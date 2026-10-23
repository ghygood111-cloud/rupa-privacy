# Third-party reuse protocol

## Purpose

This protocol is for an independent user who has not modified or developed the
RUPA source. It evaluates whether the documented package can be installed,
configured, validated, run, and interpreted without author assistance. Record
observations as written; do not convert a failed task into a success after source
editing.

## Test package

Use `examples/third_party_reuse` and a clean virtual environment. The participant
may edit only copied CSV and YAML inputs. The expected command sequence is
`pip install`, `rupa-privacy validate`, `rupa-privacy run`, and
`rupa-privacy inspect-run`.

## Participant record

1. Background and role:
2. Prior experience with differential privacy:
3. Was installation completed? Record commands, time, and any errors:
4. Could the participant identify the calibration, release, and sensitive-target columns?
5. Could the participant explain and, if requested, change one public numeric bound?
6. Could the participant explain and, if requested, change one public category domain?
7. Could the participant identify the fixed public roster and one-row-per-unit requirement?
8. Could the participant add or modify one supported public linear equality without source changes?
9. Did `validate` pass for the supplied example, and did an intentionally invalid constraint fail?
10. Was a protected release produced and accepted by `inspect-run`?
11. Could the participant interpret total epsilon, field epsilon, and final constraint residuals?
12. Total elapsed time from environment creation to inspected release:
13. Blocking issues and the exact step where each occurred:
14. Were error messages actionable? Which message was least useful?
15. Which README section was unclear, and was the task completed without modifying Python source?

## Evidence to retain

Retain the environment version, install log, command transcript, copied input
configuration, produced run manifest, participant answers, elapsed time, and any
failure screenshots or text. Do not include confidential records or participant
identifiers beyond the consented study record.

No third-party outcome is reported in this repository until a real participant
has completed this protocol.
