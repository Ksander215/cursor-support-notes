import secrets


def main() -> None:
    # Print a ready-to-paste line for .env.production.
    # NOTE: This prints a secret to your terminal. Do not commit it, do not share publicly.
    print(f"SEC_SCANNER_API_KEY=sk_{secrets.token_urlsafe(32)}")


if __name__ == "__main__":
    main()

