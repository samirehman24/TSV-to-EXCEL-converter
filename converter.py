
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from validator import validate_tsv


def convert_tsv_to_excel(
    file_path=None,
    text=None,
    output_path=None
):
    """
    Convert validated TSV data into a formatted Excel workbook.

    Returns:
        Dictionary containing output file, records and columns.
    """

    # Step 1: Validate input
    result = validate_tsv(
        file_path=file_path,
        text=text
    )

    if not result["valid"]:

        error_message = "\n".join(result["errors"])

        raise ValueError(
            "TSV validation failed:\n\n" + error_message
        )

    headers = result["headers"]
    rows = result["rows"]

    # Step 2: Check Excel limits
    if len(headers) > 16384:
        raise ValueError("Excel supports a maximum of 16,384 columns.")

    if len(rows) + 1 > 1048576:
        raise ValueError("Excel supports a maximum of 1,048,576 rows.")

    for row_number, row in enumerate([headers] + rows, start=1):
        for column_number, value in enumerate(row, start=1):
            if len(value) > 32767:
                raise ValueError(
                    f"Cell at row {row_number}, column "
                    f"{column_number} exceeds Excel's "
                    "32,767-character cell limit."
                )

    # Step 3: Determine output location
    if output_path:

        output_file = Path(output_path)

    elif file_path:

        output_file = Path(file_path).with_suffix(".xlsx")

    else:

        raise ValueError(
            "Please provide an output path when using pasted data."
        )

    if output_file.suffix.lower() != ".xlsx":
        raise ValueError("Output file must have an .xlsx extension.")

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Step 4: Create workbook
    workbook = Workbook()

    worksheet = workbook.active
    worksheet.title = "Data"

    # Step 5: Write headers
    worksheet.append(headers)

    # Step 6: Write data without changing values
    for row in rows:

        worksheet.append(row)

    # Step 7: Format headers
    header_fill = PatternFill(
        fill_type="solid",
        fgColor="217346"
    )

    header_font = Font(
        name="Arial",
        size=10,
        bold=True,
        color="FFFFFF"
    )

    for cell in worksheet[1]:

        cell.fill = header_fill
        cell.font = header_font

        cell.data_type = "s"
        cell.number_format = "@"

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True
        )

    worksheet.row_dimensions[1].height = 30

    # Step 8: Preserve all values as text
    for row in worksheet.iter_rows(min_row=2):

        for cell in row:

            cell.data_type = "s"
            cell.number_format = "@"

            cell.font = Font(
                name="Arial",
                size=10
            )

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True
            )

    # Step 9: Automatically adjust column widths
    for column_number, header in enumerate(headers, start=1):

        max_length = len(str(header))

        for row in rows:
            max_length = max(
                max_length,
                len(str(row[column_number - 1]))
            )

        worksheet.column_dimensions[
            get_column_letter(column_number)
        ].width = min(max_length + 3, 60)

    # Step 10: Excel usability settings
    worksheet.freeze_panes = "A2"

    worksheet.auto_filter.ref = worksheet.dimensions

    worksheet.sheet_view.showGridLines = True

    # Step 11: Save workbook
    workbook.save(output_file)

    return {
        "success": True,
        "output_file": str(output_file.resolve()),
        "records": len(rows),
        "columns": len(headers),
        "warnings": result["warnings"]
    }


if __name__ == "__main__":

    try:

        result = convert_tsv_to_excel(
            file_path="test_data.txt"
        )

        print("\nConversion Successful!")
        print("----------------------")
        print("Records:", result["records"])
        print("Columns:", result["columns"])
        print("Excel:", result["output_file"])

        if result["warnings"]:
            print("\nWarnings:")
            for warning in result["warnings"]:
                print("-", warning)

    except Exception as e:

        print("\nConversion Failed!")
        print(e)
