# apps/artefacts/renderers.py
import csv
from io import StringIO, BytesIO
from openpyxl import Workbook
from rest_framework.renderers import BaseRenderer

class CSVRenderer(BaseRenderer):
    media_type = 'text/csv'
    format = 'csv'
    charset = 'utf-8'
    render_style = 'binary'

    def render(self, data, media_type=None, renderer_context=None):
        if data is None:
            return ''
        if isinstance(data, dict) and 'results' in data:
            data = data['results']
        if not isinstance(data, list):
            data = [data]
        if not data:
            return ''

        headers = list(data[0].keys())
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

        # Ajout du header Content-Disposition pour le téléchargement
        if renderer_context:
            response = renderer_context.get('response')
            view = renderer_context.get('view')
            filename = getattr(view, 'export_filename', 'export.csv')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return output.getvalue()


class XLSXRenderer(BaseRenderer):
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    format = 'xlsx'
    render_style = 'binary'

    def render(self, data, media_type=None, renderer_context=None):
        if data is None:
            return b''
        if isinstance(data, dict) and 'results' in data:
            data = data['results']
        if not isinstance(data, list):
            data = [data]
        if not data:
            return b''

        wb = Workbook()
        ws = wb.active
        ws.title = "Données"

        headers = list(data[0].keys())
        ws.append(headers)
        for row in data:
            ws.append([row.get(h, '') for h in headers])

        output = BytesIO()
        wb.save(output)

        # Ajout du header Content-Disposition
        if renderer_context:
            response = renderer_context.get('response')
            view = renderer_context.get('view')
            filename = getattr(view, 'export_filename', 'export.xlsx')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return output.getvalue()
