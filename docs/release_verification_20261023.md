# RUPA 0.1.0 local release verification

Prepared on 2026-10-23. **Local verification PASS; the owner approved the 237-file clean source snapshot.** The public repository is https://github.com/ghygood111-cloud/rupa-privacy. Final release identity is recorded by the v0.1.0 tag and its release attachments; no Zenodo DOI has been assigned.

## Executed checks

| Check | Actual outcome |
| --- | --- |
| Fresh non-editable source install and final source-archive reinstall | PASS |
| Final source-archive tests | 420 passed, 0 failed, 0 skipped, 23 existing warnings |
| Fresh wheel environment and final wheel install | PASS |
| Final installed-wheel tests from extracted source archive | 420 passed, 0 failed, 0 skipped, 23 existing warnings |
| pip dependency checks and system-site isolation | PASS |
| Core compared with the 20261022 technical manuscript | All 39 Python files identical |
| Six legacy checks | Four array maximum differences 0; two release digests unchanged |
| Official, water, reuse, hazardous-waste and public Ontario examples | PASS, actual validation/run/manifest inspection |
| README CLI and Python API | PASS |
| CFF 1.2.0 official-schema validation | PASS |
| Original 25-input / 30-seed four-path protocol | 750 paired bundles, 10,500 shared states, 0 failures |
| Reproduced numerical metric columns and missing masks | Every maximum difference 0; all missing masks match |
| Default privacy safety, ledger and output separation | Included in both full suites; no safety tests disabled |

Two distribution-metadata tests were added. The old pending-license assertion was updated to check the owner-authorized license. No scientific or privacy-safety assertions were weakened. The 23 warnings are existing pandas/NumPy deprecations.

The first fresh pytest attempt failed at plugin loading because newer pytest-cov was incompatible with the old locked pluggy. Pinning pytest-cov 4.1.0 resolved it. Modern build tooling was moved to a separate environment rather than upgrading the scientific packaging lock. The failed attempt remains in the local audit log; only the final outcomes above are PASS.

## Artifact identity

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| rupa_privacy-0.1.0-py3-none-any.whl | 67400 | a58c8fb3515ae4c0c2bea4c96a3f869d70f459d1950b0f02602fbfe59804c54c |
| rupa_privacy-0.1.0.tar.gz | 2032860 | 06396b996d9c9016e24ee60811dd2fb657d10249f5f96303f81839eecf57c8ec |

Both distributions retain the paper's 39 core files. The wheel includes LICENSE and THIRD_PARTY_NOTICES.md and excludes the unsupported Studio modules, raw data caches and internal audits. Source archives provide GUI, tests, examples, protocols, public input provenance and reproduction drivers.

## Scope and remaining actions

The tests used Windows build 26200 and CPython 3.9.13. Numerical dependencies are pinned in reproducibility/requirements-release-py39.txt. This is author-local verification, not hosted CI success, a new operating-system matrix, independent-person replication or a security certification.

Code licensing is BSD-3-Clause under the owner-provided attribution 高涵（中国矿业大学）. Third-party data and dependencies retain their own licenses. Source rights are owner-attested, not an independent institutional legal opinion. Secret scans and provenance review are not comprehensive vulnerability audits.

The proposed first public tag v0.1.0 matches the paper core. The old local v0.1.1-p0 tag is a historical internal baseline and will not be pushed. Original development Git history remains local; publication will use only the approved clean file snapshot.

The owner approved the file list and completed normal GitHub authorization. Publication metadata uses the real repository and tag; the final commit and asset hashes are recorded after push. Any future Zenodo DOI must come from an actual deposit. No confidential production data, credentials, original Ontario names/addresses, external paper PDFs or OS fonts are included. No core scientific computation was modified.
