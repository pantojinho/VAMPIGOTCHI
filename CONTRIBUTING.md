# Contributing to VampGotchi

Thank you for your interest in contributing to VampGotchi! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what is best for the community
- Show empathy towards other community members

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/pantojinho/VAMPIGOTCHI/issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - System information (OS, Python version, hardware)
   - Relevant log output

### Suggesting Features

1. Check existing issues and discussions
2. Create a new issue with:
   - Clear description of the feature
   - Use case and motivation
   - Possible implementation approach (if you have ideas)

### Submitting Pull Requests

1. **Fork the repository**
2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**:
   - Follow code style guidelines
   - Add comments/documentation
   - Test your changes
4. **Commit your changes**:
   ```bash
   git commit -m "Description of changes"
   ```
   Use clear, descriptive commit messages
5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
6. **Create a Pull Request** on GitHub with:
   - Clear description of changes
   - Reference related issues
   - Screenshots (if UI changes)

## Code Style Guidelines

### Python

- Follow PEP 8 style guide
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters
- Use descriptive variable and function names
- Add docstrings to functions and classes
- Keep functions focused and relatively short

Example:
```python
def scan_bluetooth_devices(timeout=5):
    """
    Scan for nearby Bluetooth devices.
    
    Args:
        timeout: Scan duration in seconds
        
    Returns:
        List of discovered devices
    """
    # Implementation
    pass
```

### File Organization

- Keep related functionality together
- Use clear section headers with comments
- Separate configuration, functions, and main logic
- Import standard library first, then third-party, then local

### Comments and Documentation

- Write clear, concise comments
- Explain "why" not just "what"
- Update documentation when code changes
- Keep comments up-to-date with code

## Development Setup

1. **Clone your fork**:
   ```bash
   git clone https://github.com/pantojinho/VAMPIGOTCHI.git
   cd VAMPIGOTCHI
   ```

2. **Set up virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Install development dependencies**:
   ```bash
   pip install -r requirements-dev.txt  # If exists
   ```

4. **Make your changes**

5. **Test your changes**:
   - Test on actual hardware if possible
   - Test display updates
   - Test BLE scanning
   - Test web interface

## Testing

- Test all new features thoroughly
- Test edge cases and error handling
- Verify backward compatibility
- Test on actual Raspberry Pi hardware when possible

## Documentation

- Update README.md if adding features
- Update docstrings for new functions
- Add examples if applicable
- Keep configuration documentation up-to-date

## Questions?

Feel free to open an issue for questions or discussions. The community is here to help!

---

Thank you for contributing to VampGotchi! 🧛🦇

