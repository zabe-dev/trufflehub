# TruffleHub

A Python-based GitHub secret scanner that uses TruffleHog to scan repositories for exposed credentials and sensitive information.

## Features

-   Scan individual repositories, entire organizations, or user accounts
-   Automatic severity classification (critical/medium) based on file patterns
-   Support for organization member scanning
-   Fork inclusion/exclusion
-   JSON output for integration with other tools
-   Color-coded console output

## Prerequisites

-   Python 3.6+
-   [TruffleHog](https://github.com/trufflesecurity/trufflehog) installed and available in PATH
-   GitHub personal access token (optional, but recommended to avoid rate limits)

## Installation

```bash
pip install requests
```

Set your GitHub token as an environment variable:

```bash
export GITHUB_TOKEN="your_token_here"
```

## Usage

**Scan an organization:**

```bash
python trufflehub.py -org organization-name
```

**Scan a user's repositories:**

```bash
python trufflehub.py -user username
```

**Scan a single repository:**

```bash
python trufflehub.py -repo https://github.com/user/repo.git
```

**Include forks and organization members:**

```bash
python trufflehub.py -org organization-name -include-forks -include-members
```

**Save results to a directory:**

```bash
python trufflehub.py -org organization-name -output results/
```

**Show only verified secrets:**

```bash
python trufflehub.py -org organization-name -results valid
```

**Silent mode (only show findings):**

```bash
python trufflehub.py -org organization-name -silent
```

## Output

Results are classified as:

-   **Critical**: Secrets found in production code
-   **Medium**: Secrets found in test/example/demo files
-   **Clean**: No secrets detected

When using `-output`, results are saved as separate JSON files for critical and medium findings.

## License

MIT
