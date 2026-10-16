"""Run existing official Grafana/Prometheus binaries in isolated loopback-only paths."""
from pathlib import Path
import argparse
import json
import signal
import socket
import subprocess
import time

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--grafana-home',type=Path,required=True);p.add_argument('--prometheus-bin',type=Path,required=True);p.add_argument('--prometheus-port',type=int,default=9096);p.add_argument('--grafana-port',type=int,default=3016);args=p.parse_args()
    for field in ['prometheus_port','grafana_port']:
        if getattr(args,field)==0:
            with socket.socket() as s:
                s.bind(('127.0.0.1',0));setattr(args,field,s.getsockname()[1])
    for port in [args.grafana_port,args.prometheus_port]:
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1',port))==0:raise SystemExit(f'Port {port} is occupied; refusing to replace its service')
    root=Path('.').resolve();runtime=root/'.runtime/observability';runtime.mkdir(parents=True,exist_ok=True)
    (runtime/'endpoints.json').write_text(json.dumps({'prometheus_url':f'http://127.0.0.1:{args.prometheus_port}','grafana_url':f'http://127.0.0.1:{args.grafana_port}'}))
    prov=runtime/'provisioning'
    for name in ['datasources','dashboards']:(prov/name).mkdir(parents=True,exist_ok=True)
    (prov/'datasources/prometheus.yaml').write_text(f'apiVersion: 1\ndatasources:\n  - name: Model Quality Prometheus\n    uid: mql-prometheus\n    type: prometheus\n    access: proxy\n    url: http://127.0.0.1:{args.prometheus_port}\n    isDefault: true\n    editable: false\n')
    (prov/'dashboards/lab.yaml').write_text('apiVersion: 1\nproviders:\n  - name: Model Quality Lab\n    folder: Model Quality Lab\n    type: file\n    options:\n      path: '+str(root/'observability/grafana/dashboards')+'\n')
    (runtime/'prometheus.yml').write_text('global:\n  scrape_interval: 2s\nscrape_configs:\n  - job_name: model-quality-lab\n    static_configs:\n      - targets: ["127.0.0.1:7856"]\n')
    config=runtime/'grafana.ini'
    config.write_text(f'''[server]\nhttp_addr = 127.0.0.1\nhttp_port = {args.grafana_port}\n[paths]\ndata = {runtime/'grafana-data'}\nlogs = {runtime/'logs'}\nplugins = {runtime/'plugins'}\nprovisioning = {prov}\n[auth.anonymous]\nenabled = true\norg_role = Viewer\n[auth]\ndisable_login_form = true\n[users]\nallow_sign_up = false\n[analytics]\nreporting_enabled = false\ncheck_for_updates = false\n''')
    commands=[[''+str(args.prometheus_bin),'--config.file='+str(runtime/'prometheus.yml'),'--storage.tsdb.path='+str(runtime/'prom-data'),f'--web.listen-address=127.0.0.1:{args.prometheus_port}'],
              [str(args.grafana_home/'bin/grafana'),'server','--homepath',str(args.grafana_home),'--config',str(config)]]
    processes=[];logs=[]
    try:
        for name,cmd in zip(['prometheus','grafana'],commands):
            log=(runtime/f'{name}.log').open('a');logs.append(log);processes.append(subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT))
        print(f'Grafana http://127.0.0.1:{args.grafana_port}/d/model-quality-lab · Prometheus http://127.0.0.1:{args.prometheus_port}',flush=True)
        while all(p.poll() is None for p in processes):time.sleep(1)
        raise SystemExit('A service exited; inspect .runtime/observability logs')
    except KeyboardInterrupt:pass
    finally:
        for process in processes:
            if process.poll() is None:process.terminate()
        for process in processes:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
        for log in logs:log.close()

if __name__=='__main__':main()
