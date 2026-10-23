"""Fail-closed validation for public linear-equality constraints."""

import numpy as np
from scipy.optimize import linprog

from ..exceptions import ConstraintValidationError
from ..models import ConstraintValidationResult


DEFAULT_CONDITION_NUMBER_LIMIT = 1e10
_ATOL = 1e-11
_RTOL = 1e-9


def _proportional_ratio(first, second):
    pivot = int(np.argmax(np.abs(first)))
    if abs(first[pivot]) <= _ATOL:
        return None
    ratio = second[pivot] / first[pivot]
    if np.allclose(second, ratio * first, rtol=_RTOL, atol=_ATOL):
        return float(ratio)
    return None


def _independent_and_redundant_rows(matrix):
    independent = []
    redundant = []
    current = np.empty((0, matrix.shape[1]), dtype=float)
    current_rank = 0
    for index, row in enumerate(matrix):
        candidate = np.vstack([current, row])
        candidate_rank = int(np.linalg.matrix_rank(candidate))
        if candidate_rank > current_rank:
            independent.append(index)
            current = candidate
            current_rank = candidate_rank
        else:
            redundant.append(index)
    return independent, redundant


def _bounds_feasibility(matrix, rhs, schema):
    bounds = [schema.public_bounds[name] for name in schema.numeric_columns]
    result = linprog(
        np.zeros(matrix.shape[1], dtype=float),
        A_eq=matrix,
        b_eq=rhs,
        bounds=bounds,
        method="highs",
    )
    if result.status == 0:
        return "FEASIBLE_WITHIN_PUBLIC_BOUNDS", None
    if result.status == 2:
        return "INFEASIBLE_WITHIN_PUBLIC_BOUNDS", (
            "Public linear equalities have no feasible solution within the declared public bounds"
        )
    return "FEASIBILITY_CHECK_FAILED", (
        "Public-bound feasibility could not be established: " + str(result.message)
    )


def validate_physical_constraints(
    schema,
    constraints,
    condition_number_limit=DEFAULT_CONDITION_NUMBER_LIMIT,
):
    """Validate only configured public linear equalities and return PASS or FAIL.

    The function never repairs, drops, or reorders constraints. A FAIL decision is
    intended to stop a release before perturbation.
    """
    constraints = list(constraints)
    names = list(schema.numeric_columns)
    matrix = np.zeros((len(constraints), len(names)), dtype=float)
    rhs = np.zeros(len(constraints), dtype=float)
    name_to_index = {name: index for index, name in enumerate(names)}
    warnings = []
    errors = []
    unsupported = []
    constraint_names = []

    for row, constraint in enumerate(constraints):
        constraint_names.append(str(constraint.name))
        if constraint.type != "equality":
            unsupported.append(row)
            errors.append(
                "Constraint {0} uses unsupported type {1!r}; only public linear equality constraints are supported".format(
                    constraint.name, constraint.type
                )
            )
        if constraint.provenance != "public":
            unsupported.append(row)
            errors.append(
                "Constraint {0} has unsupported provenance {1!r}; constraints must be explicitly public and cannot be private, learned from release data, or unknown".format(
                    constraint.name, constraint.provenance
                )
            )
        if not constraint.coefficients:
            errors.append("Constraint {0} has no coefficients".format(constraint.name))
        for name, coefficient in constraint.coefficients.items():
            if name not in name_to_index:
                errors.append(
                    "Constraint {0} references unknown or non-numerical field {1}".format(
                        constraint.name, name
                    )
                )
                continue
            matrix[row, name_to_index[name]] = coefficient
        rhs[row] = constraint.rhs
        if not np.isfinite(constraint.tolerance) or constraint.tolerance < 0:
            errors.append(
                "Constraint {0} has an invalid tolerance".format(constraint.name)
            )

    duplicate_names = sorted(
        {name for name in constraint_names if constraint_names.count(name) > 1}
    )
    if duplicate_names:
        errors.append(
            "Constraint names must be unique: " + ", ".join(duplicate_names)
        )

    finite = bool(np.isfinite(matrix).all() and np.isfinite(rhs).all())
    if not finite:
        errors.append("Constraint matrix and right-hand side must contain only finite values")

    zero_rows = (
        np.flatnonzero(np.all(np.isclose(matrix, 0.0, atol=_ATOL), axis=1)).tolist()
        if matrix.shape[0]
        else []
    )
    zero_columns = (
        [
            names[index]
            for index in np.flatnonzero(
                np.all(np.isclose(matrix, 0.0, atol=_ATOL), axis=0)
            ).tolist()
        ]
        if matrix.shape[1]
        else []
    )
    if zero_rows:
        errors.append("Constraint system contains zero rows: " + str(zero_rows))
    if zero_columns and constraints:
        warnings.append(
            "Released numerical fields without a configured equality: "
            + ", ".join(zero_columns)
        )

    rank = 0
    augmented_rank = 0
    condition_number = 0.0
    redundant_rows = []
    conflicting_rows = []
    feasibility_status = "NOT_APPLICABLE"

    if matrix.shape[0] and finite:
        rank = int(np.linalg.matrix_rank(matrix))
        augmented_rank = int(np.linalg.matrix_rank(np.column_stack([matrix, rhs])))
        condition_number = float(np.linalg.cond(matrix))
        _, redundant_rows = _independent_and_redundant_rows(matrix)

        for first in range(len(matrix)):
            for second in range(first + 1, len(matrix)):
                ratio = _proportional_ratio(matrix[first], matrix[second])
                if ratio is None:
                    continue
                consistent = bool(
                    np.isclose(rhs[second], ratio * rhs[first], rtol=_RTOL, atol=_ATOL)
                )
                if not consistent:
                    conflicting_rows.append(
                        {"first": first, "second": second, "ratio": ratio}
                    )

        if augmented_rank > rank or conflicting_rows:
            errors.append("Linear equalities are algebraically conflicting")
        if redundant_rows:
            errors.append(
                "Redundant or linearly dependent constraint rows are unsupported: "
                + str(redundant_rows)
            )
        if not np.isfinite(condition_number) or condition_number > float(
            condition_number_limit
        ):
            errors.append(
                "Constraint matrix condition number exceeds the supported limit {0:g}".format(
                    condition_number_limit
                )
            )

        if not errors:
            feasibility_status, feasibility_error = _bounds_feasibility(
                matrix, rhs, schema
            )
            if feasibility_error:
                errors.append(feasibility_error)
        elif augmented_rank > rank or conflicting_rows:
            feasibility_status = "ALGEBRAICALLY_INFEASIBLE"
        else:
            feasibility_status = "NOT_EVALUATED_DUE_TO_VALIDATION_ERRORS"
    elif not constraints:
        warnings.append("No physical constraints are configured")

    if unsupported:
        feasibility_status = "UNSUPPORTED_CONSTRAINT_OR_PROVENANCE"

    decision = "FAIL" if errors else "PASS"
    return ConstraintValidationResult(
        matrix_rows=int(matrix.shape[0]),
        matrix_columns=int(matrix.shape[1]),
        rank=rank,
        expected_rank=int(matrix.shape[0]),
        augmented_rank=augmented_rank,
        condition_number=condition_number,
        zero_rows=zero_rows,
        zero_columns=zero_columns,
        redundant_rows=redundant_rows,
        conflicting_rows=conflicting_rows,
        feasibility_status=feasibility_status,
        warnings=warnings,
        errors=errors,
        decision=decision,
    )


def require_valid_physical_constraints(schema, constraints):
    """Return diagnostics or raise before a release can proceed."""
    result = validate_physical_constraints(schema, constraints)
    if result.decision != "PASS":
        raise ConstraintValidationError(
            "Physical-constraint validation failed: " + "; ".join(result.errors),
            result=result,
        )
    return result
