#!/usr/bin/env python3
import ast
import sys
import os
import argparse
from typing import List, Tuple, Union

# Logging levels we care about
LOGGING_LEVELS = {'debug', 'info', 'warning', 'error', 'critical', 'exception', 'log'}

class FStringToPercentTransformer(ast.NodeTransformer):
    """
    An AST transformer that finds logger.level(f"...") calls
    and converts them to logger.level("... %s ...", var1, var2).

    NOTE: Currently only transforms calls directly on logger names defined
          in `logger_names` (e.g., `logger.info(...)`, `log.debug(...)`).
          It does not handle loggers accessed as attributes
          (e.g., `self.logger.info(...)`).
    """
    def __init__(self):
        super().__init__()
        self.transformed_count = 0 # Track if any transformation occurred in a file

    def visit_Call(self, node: ast.Call) -> ast.Call:
        # Ensure we are visiting child nodes first
        self.generic_visit(node)

        # Check if it's a method call like obj.method()
        if not isinstance(node.func, ast.Attribute):
            return node

        # Check if the object being called is named 'logger' (or a common alias)
        logger_names = {'logger', 'log', 'logging'}
        # --- Limitation: Only checks for simple Name access ---
        if not isinstance(node.func.value, ast.Name) or node.func.value.id not in logger_names:
            return node
        # --- End Limitation ---

        # Check if the method name is a logging level
        level_name = node.func.attr
        if level_name not in LOGGING_LEVELS:
            return node

        # Check if there are positional arguments and the first one is an f-string
        if not node.args or not isinstance(node.args[0], ast.JoinedStr):
            return node

        fstring_node = node.args[0]
        original_other_args = node.args[1:] # Keep other positional args if any
        original_keywords = node.keywords # Keep keyword args like exc_info=True

        format_string_parts: List[str] = []
        format_args: List[ast.expr] = []

        try:
            for value_node in fstring_node.values:
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    # Literal part: escape % signs
                    format_string_parts.append(value_node.value.replace('%', '%%'))
                elif isinstance(value_node, ast.FormattedValue):
                    # Expression part {expr!s:format}
                    if value_node.conversion == 114: # '!r'
                        format_string_parts.append("%r")
                    else: # includes '!s', '!a', and no specifier
                        format_string_parts.append("%s")

                    if value_node.value is None: # Should not happen in valid code
                         print(f"Warning: FormattedValue node has no value: {ast.dump(value_node)}", file=sys.stderr)
                         # Decide how to handle - skip or use a placeholder? Using placeholder for now.
                         format_string_parts.append("{INVALID_FSTRING_VALUE}")
                         continue # Skip adding to format_args

                    format_args.append(value_node.value)
                    # Format spec (value_node.format_spec) is ignored as requested

                else:
                     # Should not happen with valid f-strings
                     print(f"Warning: Skipping unexpected node type {type(value_node)} in f-string: {ast.dump(value_node)}", file=sys.stderr)
                     format_string_parts.append("{UNEXPECTED_NODE}")


            # --- Construct the new node ---
            new_format_string = "".join(format_string_parts)
            new_args = [ast.Constant(value=new_format_string)] + format_args + list(original_other_args)

            new_call_node = ast.Call(
                func=node.func,
                args=new_args,
                keywords=original_keywords
            )

            ast.copy_location(new_call_node, node)
            ast.fix_missing_locations(new_call_node) # Important

            # Increment counter only if the node is actually different
            # Comparing AST nodes directly can be tricky, unparsing is a reliable way
            if ast.unparse(node) != ast.unparse(new_call_node):
                self.transformed_count += 1
                # Optional: Print transformation details for debugging
                # print(f"Transformed: {ast.unparse(node)} -> {ast.unparse(new_call_node)}", file=sys.stderr)

            return new_call_node

        except Exception as e:
             # Improved error reporting
             try:
                 original_code_snippet = ast.unparse(node)
             except Exception: # Unparsing might fail if node is badly formed
                 original_code_snippet = ast.dump(node) # Fallback to dump
             print(f"Error transforming node near '{original_code_snippet}': {e}", file=sys.stderr)
             # Raise the exception to signal failure for this file
             raise


def transform_source_code(source_code: str) -> Tuple[str, int]:
    """
    Parses Python source code, applies the f-string to %-string transformation
    for logger calls, and returns the modified code and transformation count.

    Requires Python 3.9+ for ast.unparse.

    Returns:
        Tuple[str, int]: (modified_source_code, number_of_transformations)

    Raises:
        SyntaxError: If the source code cannot be parsed.
        Exception: If an error occurs during transformation visit.
    """
    if sys.version_info < (3, 9):
        raise RuntimeError("This script requires Python 3.9 or later for ast.unparse functionality.")

    tree = ast.parse(source_code) # Can raise SyntaxError
    transformer = FStringToPercentTransformer()
    new_tree = transformer.visit(tree) # Can raise exceptions from visit_Call
    ast.fix_missing_locations(new_tree) # Ensure tree is valid after transforms
    modified_code = ast.unparse(new_tree)
    return modified_code, transformer.transformed_count

def process_file(filename: str) -> bool:
    """
    Reads a file, transforms its content, and writes it back if changed.

    Args:
        filename: The path to the Python file.

    Returns:
        True if the file was processed successfully (even if no changes),
        False if an error occurred.
    """
    print(f"Processing {filename}...", file=sys.stderr)
    try:
        # Read original content
        with open(filename, 'r', encoding='utf-8') as f_in:
            original_content = f_in.read()

        # Transform
        modified_content, transform_count = transform_source_code(original_content)

        # Write back if changed
        if transform_count > 0:
            print(f"  Applying {transform_count} transformation(s).", file=sys.stderr)
            with open(filename.replace('.py', '_md.py'), 'w', encoding='utf-8') as f_out:
                f_out.write(modified_content)
        else:
            print("  No transformations needed.", file=sys.stderr)

        return True

    except FileNotFoundError:
        print(f"Error: File not found: {filename}", file=sys.stderr)
        return False
    except SyntaxError as e:
        print(f"Error: Failed to parse Python code in {filename}: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"Error: Failed reading or writing file {filename}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: Unexpected error processing file {filename}: {e}", file=sys.stderr)
        # Potentially print traceback here if needed for complex errors
        # import traceback
        # traceback.print_exc()
        return False


def main():
    """
    Main function to handle command-line arguments and process files.
    """
    parser = argparse.ArgumentParser(
        description="Convert logger f-strings to %-style formatting in Python files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent('''\
        Example:
          %(prog)s my_module.py utils/helpers.py

        Note:
          - Requires Python 3.9+.
          - Modifies files in-place. Make sure you have backups or use version control.
          - Currently only transforms direct calls on 'logger', 'log', or 'logging' variables.
            Calls like 'self.logger.info(f"...")' are NOT transformed.
        ''')
    )
    parser.add_argument(
        'filenames',
        metavar='FILE',
        nargs='+', # Require one or more filenames
        help='Path(s) to Python file(s) to process.'
    )

    args = parser.parse_args()

    files_processed = 0
    files_failed = 0

    for filename in args.filenames:
        if not os.path.isfile(filename):
            print(f"Warning: Skipping non-file path: {filename}", file=sys.stderr)
            continue

        if process_file(filename):
            files_processed += 1
        else:
            files_failed += 1

    print("\n--- Summary ---", file=sys.stderr)
    print(f"Files processed: {files_processed}", file=sys.stderr)
    print(f"Files failed:    {files_failed}", file=sys.stderr)

    return 1 if files_failed > 0 else 0 # Return non-zero exit code if errors occurred

# --- Main Execution ---
if __name__ == "__main__":
    # Need textwrap for argparse epilog formatting
    import textwrap
    sys.exit(main())