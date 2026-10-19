import os

# Files or folders you want to completely skip
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "build",
    "dist",
    ".pytest_cache",
}
EXCLUDE_FILES = {"bundle.py", "repo_dump.txt"}
# Only extract text-based code/config files
ALLOWED_EXTENSIONS = {".py", ".yaml", ".yml", ".toml", ".ini", ".qss", ".txt", ".md"}


def generate_repo_dump(root_dir, output_file):
    with open(output_file, "w", encoding="utf-8") as out:
        out.write("==================================================\n")
        out.write("REPOSITORY STRUCTURE\n")
        out.write("==================================================\n\n")

        # 1. Write the directory tree layout first
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            level = root.replace(root_dir, "").count(os.sep)
            indent = " " * 4 * level
            out.write(f"{indent}{os.path.basename(root)}/\n")
            sub_indent = " " * 4 * (level + 1)
            for f in files:
                if (
                    f not in EXCLUDE_FILES
                    and os.path.splitext(f)[1] in ALLOWED_EXTENSIONS
                ):
                    out.write(f"{sub_indent}{f}\n")

        out.write("\n==================================================\n")
        out.write("FILE CONTENTS\n")
        out.write("==================================================\n\n")

        # 2. Append the actual contents of each file
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if (
                    f in EXCLUDE_FILES
                    or os.path.splitext(f)[1] not in ALLOWED_EXTENSIONS
                ):
                    continue

                file_path = os.path.join(root, f)
                relative_path = os.path.relpath(file_path, root_dir)

                out.write(f"--- START OF FILE: {relative_path} ---\n")
                try:
                    with open(file_path, "r", encoding="utf-8") as code_file:
                        out.write(code_file.read())
                except Exception as e:
                    out.write(f"[Error reading file: {e}]\n")
                out.write(f"\n--- END OF FILE: {relative_path} ---\n\n")


if __name__ == "__main__":
    current_directory = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(current_directory, "repo_dump.txt")
    generate_repo_dump(current_directory, output_path)
    print(f"Success! Your entire project is combined into: {output_path}")
