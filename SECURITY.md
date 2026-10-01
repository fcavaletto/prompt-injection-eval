# Security policy

## What this project is

`prompt-injection-eval` is research software. It measures a narrow, synthetic indirect-prompt-injection setting. It is not a vulnerability scanner, a production guardrail, or a statement that any model is safe.

## How adversarial text is handled

Dataset rows intentionally contain adversarial instructions. Those strings are inert data.

The application does not:

- execute dataset strings
- execute model responses
- pass model responses to a shell
- import code named by a case
- evaluate expressions from a case
- follow links returned by a model
- read files requested by a model
- read arbitrary environment variables
- use pickle
- expand templates with `eval` or `exec`

JSON is parsed with the standard library. Output paths are the paths you pass on the command line. Case IDs are not turned into filesystem paths. `--overwrite` replaces only `raw_results.jsonl`.

The only secret shipped with the dataset is the synthetic value `SYNTHETIC_SECRET_4C91`. Do not replace it with a real secret.

## What you should not do

Do not evaluate confidential production documents, real credentials, browser data, or private user files. Do not point the harness at systems you are not explicitly authorized to test. This dataset is not authorization to test a third-party product.

## Supported Python versions

Python 3.11 and newer. Continuous integration runs on Python 3.12.

## Reporting a vulnerability

If you find a flaw in the harness itself, open a private security advisory on the repository host or contact the maintainers through the channel listed on the repository. Please describe the version, the command you ran, and the impact. Do not include live credentials in the report.

This policy covers the evaluation code. It does not cover the behavior of third-party models or of Ollama.
