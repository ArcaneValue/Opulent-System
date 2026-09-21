"""Build a source-only package from an explicit whitelist; never include records/secrets."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]
files=['server.py','webapp.py','gunicorn.conf.py','requirements.txt','Dockerfile','railway.json','railway.env.example','.gitignore','.dockerignore','test_system.py','test_hosting.py','maintenance.py','Start Opulent.cmd','AGENTS.md','README.md','USER_GUIDE.md','RAILWAY_GUIDE.md','IMPLEMENTATION_NOTES.md','VERIFICATION.md','architecture.md']
for folder in ('public','tools'):
    files += [str(p.relative_to(root)) for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
output=root/'outputs'
output.mkdir(exist_ok=True)
target=output/'opulent-railway-source.zip'
with ZipFile(target,'w',ZIP_DEFLATED) as archive:
    for name in files:
        file=root/name
        if file.is_symlink():
            raise RuntimeError('Refusing to package a symbolic link: '+name)
        archive.write(file,Path(name).as_posix())
print('Source-only package:',target)
