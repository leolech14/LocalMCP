# Contributing to LocalMCP

We love your input! We want to make contributing to LocalMCP as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## Development Process

We use GitHub to host code, to track issues and feature requests, as well as accept pull requests.

1. Fork the repo and create your branch from `main`
2. If you've added code that should be tested, add tests
3. If you've changed APIs, update the documentation
4. Ensure the test suite passes
5. Make sure your code follows the style guidelines
6. Issue that pull request!

## Code Style

- Python: We use `black` for formatting and `flake8` for linting
- TypeScript/JavaScript: We use `prettier` and `eslint`
- Run `pre-commit install` to set up automatic formatting

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=localmcp

# Run specific test file
pytest tests/test_orchestrator.py
```

## Any contributions you make will be under the MIT Software License

When you submit code changes, your submissions are understood to be under the same [MIT License](LICENSE) that covers the project.

## Report bugs using GitHub's [issue tracker](https://github.com/leolech14/LocalMCP/issues)

We use GitHub issues to track public bugs. Report a bug by [opening a new issue](https://github.com/leolech14/LocalMCP/issues/new).

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

## License

By contributing, you agree that your contributions will be licensed under its MIT License.