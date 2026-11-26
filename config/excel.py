"""Shared XLSX responses. Call only after applying the view's access checks."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def requested(request):
    return request.method == "GET" and request.GET.get("export") == "xlsx"


def response(filename, sheets, *, text_columns=()):
    """sheets: iterable of (title, headers, rows), with rows safely typed as data."""
    workbook = Workbook(write_only=True)
    for title, headers, rows in sheets:
        sheet = workbook.create_sheet(title)
        sheet.freeze_panes = "A2"
        for index, header in enumerate(headers, 1):
            # Excel displays hashes when a date/time cannot fit in its column.
            minimum_width = 26 if "date" in str(header).casefold() else 18
            column = sheet.column_dimensions[get_column_letter(index)]
            column.width = min(45, max(minimum_width, len(header) + 3))
            if index in text_columns:
                column.number_format = "@"

        def cell(value, header=False):
            if isinstance(value, datetime) and timezone.is_aware(value):
                value = timezone.localtime(value).replace(tzinfo=None)
            if value is not None and not isinstance(value, (str, int, float, Decimal, datetime, bool)):
                value = str(value)
            if isinstance(value, str):
                value = ILLEGAL_CHARACTERS_RE.sub("", value)[:32767]
            result = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                result.data_type = "s"
            if isinstance(value, Decimal):
                result.number_format = "0.00####"
            if isinstance(value, datetime):
                result.number_format = "dd/mm/yyyy hh:mm:ss"
            if header:
                result.font = Font(bold=True, color="FFFFFF")
                result.fill = PatternFill("solid", fgColor="173F63")
            return result

        sheet.append([cell(header, header=True) for header in headers])
        count = 1
        for row in rows:
            sheet.append([cell(value) for value in row])
            count += 1
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{count}"
    output = BytesIO()
    workbook.save(output)
    result = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    result["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    result["Cache-Control"] = "private, no-store"
    return result
