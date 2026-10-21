import json

import pytest

import configure_model as config


def test_fresh_configuration_encrypts_key_and_initializes_ledger(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'protect',lambda value:'encrypted-offline-value')
    locked=[]
    monkeypatch.setattr(config,'restrict_acl',lambda path:locked.append(path.name))
    path=config.write_configuration(tmp_path,'https://gateway.example.invalid/v1/','offline-model','offline-test-key')
    saved=json.loads(path.read_text())
    assert saved['api_key_dpapi']=='encrypted-offline-value'
    assert 'offline-test-key' not in path.read_text() and 'api_key' not in saved
    assert saved['base_url']=='https://gateway.example.invalid/v1' and locked==['model.pending']
    ledger=json.loads((tmp_path/'.local/live-acceptance-20261022/budget.json').read_text())
    assert ledger['limit'] is None and ledger['attempts']==0


def test_reconfiguration_requires_explicit_replace_and_preserves_usage(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'protect',lambda value:'encrypted-offline-value')
    monkeypatch.setattr(config,'restrict_acl',lambda path:None)
    path=config.write_configuration(tmp_path,'https://gateway.example.invalid/v1','first','offline-test-key')
    ledger=tmp_path/'.local/live-acceptance-20261022/budget.json'
    history={'limit':None,'attempts':400,'requests':[{'number':400,'status':'responded'}]}
    ledger.write_text(json.dumps(history))
    with pytest.raises(FileExistsError):
        config.write_configuration(tmp_path,'https://gateway.example.invalid/v1','second','offline-test-key')
    assert json.loads(path.read_text())['model']=='first'
    config.write_configuration(tmp_path,'https://gateway.example.invalid/v1','second','offline-test-key',replace=True)
    assert json.loads(path.read_text())['model']=='second'
    assert json.loads(ledger.read_text())==history


def test_acl_failure_preserves_previous_configuration(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'protect',lambda value:'encrypted-offline-value')
    monkeypatch.setattr(config,'restrict_acl',lambda path:None)
    path=config.write_configuration(tmp_path,'https://gateway.example.invalid/v1','first','offline-test-key')
    before=path.read_bytes()
    def denied(path):raise PermissionError('offline ACL failure')
    monkeypatch.setattr(config,'restrict_acl',denied)
    with pytest.raises(PermissionError):
        config.write_configuration(tmp_path,'https://gateway.example.invalid/v1','second','offline-test-key',replace=True)
    assert path.read_bytes()==before and not (tmp_path/'.local/model.pending').exists()
