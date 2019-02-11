""" Tests for vault"""

def mock_get_keyvault_secret(keyvault, secret_key, vaulttoken):
    return {'value': 'secret'}


def mock_get_vault_access_token(tenant_id, vault_client_id, client_secret=None):
    return 'abcd_token'


def mock_config_value(section, key, default=None):
    if key == 'type':
        return 'azure'
    elif key == 'client_id':
        return 'client_id'
    elif key == 'client_secret':
        return 'client_secret'
    elif key == 'tenant_id':
        return 'tenant_id'
    elif key == 'keyvault':
        return 'keyvault'
    return 'pytestdb'


def test_get_vault_data(monkeypatch):
    monkeypatch.setattr('processor.connector.vault.config_value', mock_config_value)
    monkeypatch.setattr('processor.connector.vault.get_vault_access_token', mock_get_vault_access_token)
    monkeypatch.setattr('processor.connector.vault.get_keyvault_secret', mock_get_keyvault_secret)
    from processor.connector.vault import get_vault_data
    val = get_vault_data(None)
    assert val is None
    val = get_vault_data('abcd')
    assert val == 'secret'


def test_get_azure_vault_data(monkeypatch):
    monkeypatch.setattr('processor.connector.vault.config_value', mock_config_value)
    monkeypatch.setattr('processor.connector.vault.get_vault_access_token', mock_get_vault_access_token)
    monkeypatch.setattr('processor.connector.vault.get_keyvault_secret', mock_get_keyvault_secret)
    from processor.connector.vault import get_azure_vault_data
    val = get_azure_vault_data(None)
    assert val is None
    val = get_azure_vault_data('abcd')
    assert val == 'secret'

