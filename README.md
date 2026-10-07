# OpenBao Ansible filter

This repository provides a small Ansible filter plugin for reading secrets from OpenBao (or Vault-compatible APIs) into playbooks and templates.

The filter is implemented in `openbao.py` and exposes a single filter named `openbao`.

## What it does

The filter:

- reads a secret path from OpenBao
- supports KV v2 and KV v1 layouts
- optionally selects a single field from the secret payload
- resolves connection settings from environment variables or explicit arguments
- raises a clear AnsibleFilterError when required configuration is missing or the secret cannot be read

## Installation

Place the repository directory or the `openbao.py` file in your Ansible `filter_plugins` directory.

Example layout:

```text
playbook.yml
filter_plugins/
  openbao.py
```

Then configure Ansible to load that directory by setting `filter_plugins` in `ansible.cfg`:

```ini
[defaults]
filter_plugins = ./filter_plugins
```

If you prefer to use a project-local directory, keep the file there and reference that directory from your `ansible.cfg` file.

## Usage

The filter accepts these arguments:

```jinja2
{{ 'secret/myapp/database' | openbao('password') }}
```

The function signature is:

```python
openbao(path, field=None, mount_point='kv', version=None, addr=None, token=None, namespace=None, timeout=10)
```

### Parameters

- `path`: secret path to read
- `field`: field to return from the secret data; if omitted and the secret has exactly one key, that value is returned
- `mount_point`: mount path, default `kv`
- `version`: KV secret version to read, when supported
- `addr`: OpenBao server URL; if omitted, it falls back to `OPENBAO_ADDR`, `BAO_ADDR`, or `VAULT_ADDR`
- `token`: OpenBao token; if omitted, it falls back to `OPENBAO_TOKEN`, `BAO_TOKEN`, or `VAULT_TOKEN`
- `namespace`: optional namespace; if omitted, it falls back to `OPENBAO_NAMESPACE`, `BAO_NAMESPACE`, or `VAULT_NAMESPACE`
- `timeout`: HTTP timeout in seconds, default `10`

## Examples

### Read a single field

```yaml
vars:
  db_password: "{{ 'secret/app/db' | openbao('password') }}"
```

### Use a custom mount point

```yaml
vars:
  api_token: "{{ 'myapp/service-account' | openbao('token', mount_point='secret') }}"
```

### Pass connection settings explicitly

```yaml
vars:
  bao_token: !vault |
    $ANSIBLE_VAULT;1.1;AES256
    ...
  db_password: >-
    {{ 'secret/app/db' | openbao('password', addr='https://bao.example.com', token=bao_token, namespace='team-a') }}
```

### Read a specific secret version

```yaml
vars:
  previous_password: >-
    {{ 'secret/app/db' | openbao('password', version=2) }}
```

## Environment variables

These are supported automatically:

```bash
export OPENBAO_ADDR="https://bao.example.com"
export OPENBAO_TOKEN="s.abc123"
export OPENBAO_NAMESPACE="team-a"
```

Legacy aliases are also accepted:

```bash
export BAO_ADDR="https://bao.example.com"
export BAO_TOKEN="s.abc123"
export BAO_NAMESPACE="team-a"

export VAULT_ADDR="https://bao.example.com"
export VAULT_TOKEN="s.abc123"
export VAULT_NAMESPACE="team-a"
```

## Behavior notes

- Paths are normalized to work with a mount point and secret path.
- The plugin tries the KV v2 endpoint first, then falls back to KV v1 when it sees a 400, 404, or 405 response. A 400 can still indicate a real configuration mistake, so check the server response when troubleshooting version mismatches.
- If the secret contains multiple keys and `field` is not provided, the filter raises an error listing the available keys.
- Secrets with a single key can be returned directly without explicitly naming the field.

## Example playbook

```yaml
- hosts: localhost
  gather_facts: false
  tasks:
    - debug:
        msg: "Database password is {{ 'secret/app/db' | openbao('password') }}"
```

This assumes your `ansible.cfg` contains:

```ini
[defaults]
filter_plugins = ./filter_plugins
```

## License

This project does not currently declare a license file or package metadata, so use it in accordance with the repository owner’s terms.
