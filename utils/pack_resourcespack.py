#!/usr/bin/env python3
"""
Standalone Resource Pack Packer (Hardened)

Creates a distributable ZIP file of a Minecraft resource pack.

Expected project structure:
.
├── LICENSE
├── pack/
└── utils/
    └── pack_resourcepack.py

Co-developed with Qwen3-Max
"""

import sys
import zipfile
import shutil
import logging
import os
import shlex
from pathlib import Path
import argparse


def setup_logger(log_file=None):
    logger = logging.getLogger("ResourcePackPacker")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    if log_file:
        # Expand ~ in log file path
        log_path = Path(os.path.expanduser(log_file)).resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
        )
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        logger.info(f"Logging to file: {log_path}")

    return logger


def parse_user_path(raw):
    """Safely parse path with quotes and expand ~."""
    if not raw:
        return raw
    try:
        parts = shlex.split(raw)
        path_str = parts[0] if parts else raw
    except ValueError:
        path_str = raw.strip()
        for quote in ('"', "'"):
            if path_str.startswith(quote) and path_str.endswith(quote):
                path_str = path_str[1:-1]
    # Expand ~ and resolve
    return Path(os.path.expanduser(path_str)).resolve()


def copy_directory(src, dst):
    """Recursively copy directory (safe, Python <3.8 compatible)."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.is_dir():
            copy_directory(item, dst / item.name)
        else:
            shutil.copy2(item, dst / item.name)


def create_zip_from_dir(source_dir, zip_path, logger):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(source_dir)
                # Basic Zip Slip protection
                if ".." in str(arcname) or str(arcname).startswith("/"):
                    logger.warning(f"Skipped unsafe path in ZIP: {arcname}")
                    continue
                zf.write(file_path, arcname)
    logger.info(f"Successfully created: {zip_path.name}")


def confirm_choice(prompt, default=False):
    while True:
        choice = (
            input(f"{prompt} (y/n) [default: {'y' if default else 'n'}]: ")
            .strip()
            .lower()
        )
        if choice == "":
            return default
        elif choice in ("y", "yes"):
            return True
        elif choice in ("n", "no"):
            return False
        else:
            print("Please enter 'y' or 'n'.")


def get_input_with_default(prompt, default=""):
    if default:
        raw = input(f"{prompt} (default: {default}): ").strip()
        return raw if raw else default
    else:
        while True:
            raw = input(f"{prompt}: ").strip()
            if raw:
                return raw
            print("Input cannot be empty.")


def interactive_mode(logger):
    print("=" * 50)
    print("Minecraft Resource Pack Packer")
    print("=" * 50)
    print("This tool creates a distributable ZIP file.")
    print()

    # Source directory
    source_default = "pack"
    source_raw = get_input_with_default(
        "Enter path to resource pack directory", default=source_default
    )
    source_dir = parse_user_path(source_raw)
    if not source_dir.exists():
        logger.error(f"Error: Source path does not exist: {source_dir}")
        sys.exit(1)
    if not source_dir.is_dir():
        logger.error(f"Error: Source is not a directory: {source_dir}")
        sys.exit(1)
    if not os.access(source_dir, os.R_OK):
        logger.error(f"Error: No read permission on source: {source_dir}")
        sys.exit(1)

    # LICENSE
    license_path = source_dir.parent / "LICENSE"
    if not license_path.exists():
        logger.error(f"Error: LICENSE not found at: {license_path}")
        logger.error("Ensure a LICENSE file exists in your project root.")
        sys.exit(1)
    if not os.access(license_path, os.R_OK):
        logger.error(f"Error: Cannot read LICENSE file: {license_path}")
        sys.exit(1)
    logger.info(f"Using LICENSE from: {license_path}")

    # Panorama
    include_panorama = confirm_choice("Include panorama background?", default=False)

    # Output path + filename
    output_default = str(Path.cwd() / "resource_pack.zip")
    output_raw = get_input_with_default(
        "Enter full output path including filename (.zip extension optional)",
        default=output_default,
    )
    output_path = parse_user_path(output_raw)
    if not output_path.suffix.lower() == ".zip":
        output_path = output_path.with_suffix(".zip")

    # Check output parent permissions
    output_parent = output_path.parent
    if not output_parent.exists():
        try:
            output_parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Error: Cannot create output directory: {e}")
            sys.exit(1)
    if not os.access(output_parent, os.W_OK):
        logger.error(f"Error: No write permission in output directory: {output_parent}")
        sys.exit(1)

    return source_dir, license_path, include_panorama, output_path


def main():
    parser = argparse.ArgumentParser(description="Pack a Minecraft resource pack.")
    parser.add_argument("--source", "-s", type=str, help="Resource pack directory")
    parser.add_argument(
        "--output", "-o", type=str, help="Full output path (e.g., ./pack.zip)"
    )
    parser.add_argument(
        "--include-panorama", action="store_true", help="Include panorama"
    )
    parser.add_argument("--license", type=str, help="Path to LICENSE file")
    parser.add_argument("--log-file", type=str, help="Log to file")
    parser.add_argument("--non-interactive", action="store_true", help="Batch mode")
    args = parser.parse_args()

    logger = setup_logger(args.log_file)

    if not args.non_interactive:
        source_dir, license_path, include_panorama, output_path = interactive_mode(
            logger
        )
    else:
        if not args.source or not args.output:
            logger.error(
                "Error: --source and --output required in non-interactive mode."
            )
            sys.exit(1)

        source_dir = parse_user_path(args.source)
        if not source_dir.exists() or not source_dir.is_dir():
            logger.error(f"Error: Invalid source: {source_dir}")
            sys.exit(1)
        if not os.access(source_dir, os.R_OK):
            logger.error(f"Error: No read permission on source: {source_dir}")
            sys.exit(1)

        license_path = (
            parse_user_path(args.license)
            if args.license
            else source_dir.parent / "LICENSE"
        )
        if not license_path.exists():
            logger.error(f"Error: LICENSE not found: {license_path}")
            sys.exit(1)
        if not os.access(license_path, os.R_OK):
            logger.error(f"Error: Cannot read LICENSE: {license_path}")
            sys.exit(1)

        output_path = parse_user_path(args.output)
        if not output_path.suffix.lower() == ".zip":
            output_path = output_path.with_suffix(".zip")
        output_parent = output_path.parent
        if not output_parent.exists():
            output_parent.mkdir(parents=True, exist_ok=True)
        if not os.access(output_parent, os.W_OK):
            logger.error(f"Error: No write permission in: {output_parent}")
            sys.exit(1)

        include_panorama = args.include_panorama

    # Packing
    temp_dir = output_path.parent / ".temp_pack"
    try:
        logger.info("Copying resource pack files...")
        copy_directory(source_dir, temp_dir)
        shutil.copy2(license_path, temp_dir / "LICENSE")

        if not include_panorama:
            panorama_dir = (
                temp_dir
                / "assets"
                / "minecraft"
                / "textures"
                / "gui"
                / "title"
                / "background"
            )
            if panorama_dir.exists():
                shutil.rmtree(panorama_dir)
                logger.info("Panorama background removed.")
            else:
                logger.info("No panorama background found.")

        create_zip_from_dir(temp_dir, output_path, logger)
        mode = "with panorama" if include_panorama else "without panorama"
        logger.info(f"\nPacking complete! ({mode})")
        logger.info(f"Output: {output_path}")

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(1)
