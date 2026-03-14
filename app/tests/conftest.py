# conftest.py — Exclude files that are not real test suites
collect_ignore = [
    "test_donations.py",  # code-migration notes, not tests
    "test_email.py",      # standalone script, not a pytest suite
]
