# MAGIC Workshop Ansible Deployment

> Regarding the Workshop data:
> The simulated data used to create this workshop is specifically not uploaded to this repository.
> Everybody that wants to investigate on the presented case from the workshop, please reach out to us. 
> We will be happy to share the exported data with you for your investigation.
> Please contact Alexander.Goedeke@sva.de.
 
This repository contains the workshop stack directly in
`roles/magic-workshop/files/workshop/`. Ansible copies those files to the host and performs the complete
setup, including Docker Compose startup, participant provisioning, and
automatic Let's Encrypt certificate issuance and renewal.

## Configure

Add one host per VM in [`inventories/hosts.yml`](inventories/hosts.yml). For
each VM, set:

- `ansible_host`: the VM's public IP or DNS name
- `workshop_domain`: the public domain pointing to that VM
- `workshop_participants_csv_path`: CSV path on the Ansible controller; relative
    paths are resolved from this repository's root

The CSV is copied to the VM before provisioning. If its file does not exist,
Ansible creates it locally with 20 rows (`participant01` through
`participant20`), ready to edit. Password columns can be left empty to have
strong passwords generated. CSV files are git-ignored; the example inventory
uses `.participants/` for them.

Shared values belong in [`group_vars/all.yml`](group_vars/all.yml): workshop
user and directory, Let's Encrypt notification email, and the MAGIC app
credentials.
It contains credentials in plain text; keep real values private and out of
commits.

The certificate authority must be able to resolve each domain to its VM and
reach inbound TCP ports 80 and 443.

## Deploy

Replace the sample IP addresses and domains in the inventory, fill in the
shared credentials, then run the playbook. Ansible deploys every host in the
`workshops` group; use `--limit` to deploy only selected VMs.

```sh
ansible-playbook playbooks/main.yml
```

On later runs, existing data and participant credentials are reused. A systemd
timer checks for certificate renewal twice daily and reloads nginx after
renewal.