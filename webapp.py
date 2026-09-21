"""Hosted WSGI entry point, reusing the local pilot's API and permission checks."""
import atexit
import io
import json
import os
import threading
from types import SimpleNamespace
from urllib.parse import urlparse

from flask import Flask, Response, request

import server


def create_app(start_worker=None):
    if start_worker is None:
        start_worker = os.environ.get('OPULENT_EXTERNAL_WORKER', '') != '1'
    public = os.environ.get('OPULENT_PUBLIC_URL','').rstrip('/')
    parsed = urlparse(public)
    if public and (parsed.scheme!='https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise RuntimeError('OPULENT_PUBLIC_URL must be an HTTPS origin without a path.')
    if (os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_ENVIRONMENT_NAME')) and not public:
        raise RuntimeError('Set OPULENT_PUBLIC_URL to the Railway HTTPS domain.')
    if public and len(os.environ.get('OPULENT_SETUP_TOKEN',''))<24:
        raise RuntimeError('Set a private OPULENT_SETUP_TOKEN of at least 24 characters.')
    if public and not (os.environ.get('DATABASE_URL') or (os.environ.get('OPULENT_DB') and os.environ.get('OPULENT_BACKUPS'))):
        raise RuntimeError('Configure DATABASE_URL for PostgreSQL, or both OPULENT_DB and OPULENT_BACKUPS for the SQLite pilot.')
    server.init_db()
    app=Flask(__name__,static_folder=None)
    app.config['MAX_CONTENT_LENGTH']=100000
    stop=threading.Event()
    worker=None
    if start_worker:
        worker=threading.Thread(target=server.worker_loop,args=(stop,),daemon=True)
        worker.start()
        atexit.register(stop.set)
    app.extensions['opulent_worker']=worker
    app.extensions['opulent_stop']=stop

    @app.get('/healthz')
    def health():
        try:
            with server.connect() as c:
                c.execute('SELECT 1').fetchone()
            if worker is not None and not worker.is_alive():
                raise RuntimeError('Worker stopped')
            return {'status':'ok','version':server.VERSION,'sms_mode':'simulation'}
        except Exception:
            return {'status':'unhealthy'},503

    @app.route('/',defaults={'path':''},methods=['GET','POST'])
    @app.route('/<path:path>',methods=['GET','POST'])
    def dispatch(path):
        # Adapt the already-tested handler to Flask/Gunicorn's WSGI request.
        handler=object.__new__(server.Handler)
        handler.headers=request.headers
        handler.path=request.full_path.rstrip('?')
        handler.rfile=io.BytesIO(request.get_data())
        handler.client_address=(request.remote_addr or 'unknown',0)
        handler.server=SimpleNamespace(server_port=int(os.environ.get('PORT','8080')))
        output=[]

        def reply(value,status=200,cookie=None,content_type='application/json'):
            raw=json.dumps(value).encode() if content_type=='application/json' else value
            response=Response(raw,status=status,content_type=content_type)
            response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['Referrer-Policy']='same-origin'
            response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            if cookie:
                response.headers['Set-Cookie']=cookie
            if public:
                response.headers['Strict-Transport-Security']='max-age=31536000'
            output.append(response)

        handler.reply=reply
        if request.method=='POST':
            handler.do_POST()
        else:
            handler.do_GET()
        return output[0]

    @app.errorhandler(413)
    def large_request(error):
        return {'error':'Request is too large.'},413

    @app.errorhandler(500)
    def server_error(error):
        return {'error':'An internal operation failed.'},500

    return app
