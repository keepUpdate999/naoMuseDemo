"""Configure a fresh Windows checkout without exposing a key in argv or Git."""
import argparse
import getpass
import json
from pathlib import Path
import subprocess

from secret_store import protect


def restrict_acl(path):
    who=subprocess.check_output(['whoami'],text=True).strip()
    subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',f'{who}:(F)'],
                   check=True,capture_output=True)


def write_configuration(root,base_url,model,api_key,provider='openai',replace=False):
    local=Path(root)/'.local'
    path=local/'model.json'
    if path.exists() and not replace:
        raise FileExistsError('Existing model configuration preserved; use --replace to change it.')
    if not api_key.strip() or not model.strip() or not base_url.startswith(('http://','https://')):
        raise ValueError('A valid base URL, model and non-empty API key are required.')
    local.mkdir(parents=True,exist_ok=True)
    # The on-disk document contains only DPAPI ciphertext, never the plaintext key.
    value={'enabled':True,'provider':provider,'base_url':base_url.rstrip('/'),
           'model':model,'api_key_dpapi':protect(api_key.strip()),'max_tokens':1024}
    temp=local/'model.pending'
    try:
        temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        restrict_acl(temp)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    ledger=local/'live-acceptance-20261022/budget.json'
    if not ledger.exists():
        ledger.parent.mkdir(parents=True,exist_ok=True)
        ledger.write_text(json.dumps({'limit':None,'attempts':0,'responses':0,
            'input_tokens':0,'output_tokens':0,'requests':[]},indent=2),encoding='utf-8')
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--provider',choices=['openai','anthropic'],default='openai')
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if (root/'.local/model.json').exists() and not args.replace:
        parser.error('Existing model configuration preserved; use --replace to change it.')
    key=getpass.getpass('API Key (hidden): ')
    write_configuration(root,args.base_url,args.model,key,args.provider,args.replace)
    print('Local encrypted configuration saved. No model request was sent.')


if __name__=='__main__':main()
