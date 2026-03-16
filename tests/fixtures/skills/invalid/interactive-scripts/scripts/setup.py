"""Setup script — intentionally uses interactive input to trigger the check."""
import getpass

project_name = input("Enter project name: ")
api_key = getpass.getpass("Enter API key: ")

print(f"Setting up {project_name}...")
