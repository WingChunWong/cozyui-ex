#!/usr/bin/env python3
"""
Minecraft Mod Assets Extractor

Extracts 'assets/' from mod JARs, including nested dependencies.

Co-developed with Qwen3-Max
"""

import os
import sys
import zipfile
import shutil
import tempfile
import logging
import shlex
from pathlib import Path
from typing import Set, Optional
import argparse


class ModAssetsExtractor:
    def __init__(self, log_file: Optional[str] = None, recursive: bool = False):
        self.recursive = recursive
        self.logger = logging.getLogger("ModAssetsExtractor")
        self._setup_logging(log_file)
        self.processed_jars: Set[str] = set()

    def _setup_logging(self, log_file: Optional[str]) -> None:
        self.logger.handlers.clear()
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter("%(message)s"))
        console.setLevel(logging.INFO)
        self.logger.addHandler(console)

        if log_file:
            log_path = Path(log_file).expanduser().resolve()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
            )
            file_handler.setLevel(logging.DEBUG)
            self.logger.addHandler(file_handler)
            self.logger.info(f"Logging to file: {log_path}")

    @staticmethod
    def _parse_user_path(raw: str) -> str:
        """Safely parse quoted paths from user input."""
        if not raw:
            return raw
        try:
            parts = shlex.split(raw)
            return parts[0] if parts else raw
        except ValueError:
            cleaned = raw.strip()
            if len(cleaned) >= 2:
                if (cleaned.startswith('"') and cleaned.endswith('"')) or (
                    cleaned.startswith("'") and cleaned.endswith("'")
                ):
                    cleaned = cleaned[1:-1]
            return cleaned

    @staticmethod
    def _is_safe_path(basedir: Path, member: str) -> bool:
        """Prevent Zip Slip."""
        try:
            resolved = (basedir / member).resolve()
            return str(resolved).startswith(str(basedir.resolve()))
        except Exception:
            return False

    def _extract_jar(self, jar_path: Path, output_dir: Path, depth: int = 0) -> bool:
        """Recursively extract assets from JAR (including nested JARs)."""
        indent = "  " * depth
        jar_abs = jar_path.resolve()
        if str(jar_abs) in self.processed_jars:
            self.logger.info(f"{indent}Skipping already processed: {jar_path.name}")
            return True
        self.processed_jars.add(str(jar_abs))

        jar_type = "Main Mod" if depth == 0 else "Nested Mod"
        self.logger.info(f"{indent}Processing {jar_type}: {jar_path.name}")

        zip_kwargs = {}
        if sys.version_info >= (3, 11):
            zip_kwargs["metadata_encoding"] = "utf-8"

        try:
            with zipfile.ZipFile(jar_path, "r", **zip_kwargs) as jar:
                asset_members = [m for m in jar.namelist() if m.startswith("assets/")]
                if asset_members:
                    folder = jar_path.stem if depth == 0 else f"nested_{jar_path.stem}"
                    mod_out = output_dir / folder
                    mod_out.mkdir(parents=True, exist_ok=True)
                    count = 0
                    for member in asset_members:
                        if self._is_safe_path(mod_out, member):
                            jar.extract(member, mod_out)
                            count += 1
                        else:
                            self.logger.warning(
                                f"{indent}Skipped unsafe path: {member}"
                            )
                    self.logger.info(f"{indent}Extracted {count} file(s) to: {mod_out}")
                else:
                    self.logger.info(f"{indent}No 'assets/' found.")

                # Process nested JARs: allow META-INF/jars/
                nested = [
                    m
                    for m in jar.namelist()
                    if m.endswith(".jar")
                    and (
                        not m.startswith("META-INF/") or m.startswith("META-INF/jars/")
                    )
                ]
                if nested:
                    self.logger.info(f"{indent}Found {len(nested)} nested JAR(s).")
                    with tempfile.TemporaryDirectory() as tmp:
                        for nj in nested:
                            safe_name = nj.replace("/", "_").replace("\\", "_")
                            nested_path = Path(tmp) / safe_name
                            with jar.open(nj) as src, open(nested_path, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            self._extract_jar(nested_path, output_dir, depth + 1)
                elif depth > 0:
                    self.logger.info(f"{indent}Finished nested JAR.")

                return True

        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, OSError) as e:
            self.logger.error(f"{indent}JAR processing failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"{indent}Unexpected error: {e}")
            return False

    def validate_paths(
        self, input_str: str, output_str: Optional[str], batch: bool
    ) -> tuple[Path, Path]:
        """Expand ~, validate existence, type, and permissions."""
        input_path = Path(self._parse_user_path(input_str)).expanduser().resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
        if not input_path.is_dir():
            raise NotADirectoryError(f"Input is not a directory: {input_path}")
        if not os.access(input_path, os.R_OK):
            raise PermissionError(f"No read permission on: {input_path}")

        output_path = (
            Path(self._parse_user_path(output_str) if output_str else "")
            .expanduser()
            .resolve()
            if output_str
            else (input_path / "extracted_assets")
        )

        parent = output_path.parent
        if not parent.exists():
            raise FileNotFoundError(f"Output parent missing: {parent}")
        if not os.access(parent, os.W_OK):
            raise PermissionError(f"No write permission in: {parent}")
        if output_path.exists() and not os.access(output_path, os.W_OK):
            raise PermissionError(f"Output dir not writable: {output_path}")

        if output_path.exists():
            msg = f"[WARNING] Output directory exists. Clear it?"
            if not (batch or self._confirm_action(msg)):
                raise SystemExit("Operation cancelled.")
            shutil.rmtree(output_path)

        return input_path, output_path

    def _confirm_action(self, message: str, batch: bool = False) -> bool:
        if batch:
            return True
        while True:
            choice = input(f"{message} (y/n): ").strip().lower()
            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            print("Please enter 'y' or 'n'.")

    def get_input_with_default(self, prompt: str, default: Optional[str] = None) -> str:
        if default is not None:
            raw = input(f"{prompt} (default: {default}): ").strip()
            return raw if raw else default
        while True:
            raw = input(f"{prompt}: ").strip()
            if raw:
                return raw
            print("Input cannot be empty.")

    def interactive_mode(
        self, prefill_in: Optional[str] = None, prefill_out: Optional[str] = None
    ):
        print("=" * 40)
        print("Minecraft Mod Assets Extraction Tool")
        print("=" * 40)
        while True:
            inp = self.get_input_with_default(
                "Input directory with mod JARs", prefill_in
            )
            out = self.get_input_with_default("Output directory", prefill_out)
            try:
                return self.validate_paths(inp, out, batch=False)
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                print(f"[ERROR] {e}\nPlease try again.\n")

    def run(self, input_path: Path, output_path: Path, batch: bool = False):
        output_path.mkdir(parents=True, exist_ok=True)

        # Scan JARs: recursive or top-level only
        if self.recursive:
            jars = list(input_path.rglob("*.jar"))
        else:
            jars = list(input_path.glob("*.jar"))

        if not jars:
            raise FileNotFoundError("No '.jar' files found.")

        if not batch:
            print(f"\n[INFO] Found {len(jars)} JAR(s).")
            if not self._confirm_action("Proceed?", batch):
                raise SystemExit("Cancelled.")

        print("\n[INFO] Starting extraction...\n")
        success = error = 0
        for i, jar in enumerate(jars, 1):
            print(f"\n--- Processing {i}/{len(jars)} ---")
            if self._extract_jar(jar, output_path):
                success += 1
            else:
                error += 1

        print("\n" + "=" * 40)
        print("Extraction completed.")
        print(f"Successful: {success}")
        print(f"Failed:     {error}")
        print(f"Assets saved to: {output_path}")
        print("=" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="Extract Minecraft mod assets (with nested JAR support)."
    )
    parser.add_argument("--input", "-i", help="Input directory containing mod JARs")
    parser.add_argument("--output", "-o", help="Output directory for extracted assets")
    parser.add_argument(
        "--interactive", action="store_true", help="Force interactive mode"
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Recursively scan subdirectories for JAR files",
    )
    parser.add_argument("--log-file", help="Enable detailed logging to a file")
    args = parser.parse_args()

    extractor = ModAssetsExtractor(log_file=args.log_file, recursive=args.recursive)

    try:
        if args.interactive:
            inp, out = extractor.interactive_mode(args.input, args.output)
            extractor.run(inp, out, batch=False)
        elif args.input:
            inp, out = extractor.validate_paths(args.input, args.output, batch=True)
            extractor.run(inp, out, batch=True)
        else:
            inp, out = extractor.interactive_mode()
            extractor.run(inp, out, batch=False)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        extractor.logger.fatal(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
