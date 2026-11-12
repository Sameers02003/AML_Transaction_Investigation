def mask(ref: str) -> str:
    """acct_demo_101 -> acct_***101. Use for logs and read-only views."""
    return ref if len(ref) <= 8 else ref[:5] + "***" + ref[-3:]