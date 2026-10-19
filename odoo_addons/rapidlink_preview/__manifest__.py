{
    'name': 'Rapid Link: Office preview',
    'summary': 'Preview Word, Excel, PowerPoint and OpenOffice attachments in the Odoo file viewer.',
    'description': """
Adds Word / Excel / PowerPoint / OpenOffice / CSV files to the standard attachment viewer.

When an employee opens such a file, Odoo checks their access, sends the file to the render service
(PDF Display) and shows the result in the viewer. The render service keeps the file only in memory
for 5 minutes; nothing is stored there.

System parameters:

* ``rapidlink_preview.url`` - render service address, e.g. https://pdf.example.com
* ``rapidlink_preview.secret`` - render service key (PD_RENDER_TOKEN on the render server)
""",
    'version': '18.0.1.1.0',
    'author': 'Rapid Link SRL',
    'license': 'LGPL-3',
    'category': 'Productivity',
    'depends': ['web', 'mail'],
    'data': [
        'data/config.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rapidlink_preview/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
