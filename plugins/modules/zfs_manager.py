#!/bin/python3
DOCUMENTATION = r'''
---
module: kuit_zfs

short_description: Module for working with zpools
version_added: "1.0.0"
description: Module for creating, deleting, exporting and importing zpools.

options:
    name:
        description: Name of the zpool
        required: true
        type: str
    type:
        description: zvol or zpool
        required: false
        default: zpool
        type: str
    size:
        description: size of zvol
        required: false
        type: str
    state:
            -   present
            -   absent
            -   export
            -   import
        required: false
        default: present
        type: str
    raidz:
            -   stripe
            -   mirror
            -   raidz
            -   raidz2
            -   raidz3
        required: false
        default: stripe
        type: str
    disks:
        description: List of disks
        required: true
        type: list
    compression:
            -   true
            -   false
        required: false
        default: false
        type: bool
    canmount:
            -   true
            -   false
        required: false
        default: false
        type: bool

author:
    - Henrik Ursin (@yourGitHubHandle)
'''

EXAMPLES = r'''
#Create zpool
- name: Zfs facts
  kuit_zfs::
    name: dstor0
    type: raidz2
    disks: 
        -   sda
        -   sdb
        -   sdc
    compression: true
    canmount: false
    state: present

#Delete zpool
- name: Zfs facts
  kuit_zfs::
    name: dstor0
    state: absent

#Export zpool
- name: Zfs facts
  kuit_zfs::
    name: dstor0
    state: export

#DImport zpool
- name: Zfs facts
  kuit_zfs::
    name: dstor0
    state: import
'''

import subprocess
from ansible.module_utils.basic import AnsibleModule
from typing import List

def run_command(command: List[str], module: AnsibleModule, error_msg: str) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        module.fail_json(msg=error_msg)

def create_zpool(name: str, raid_type: str, disks: List[str], module: AnsibleModule) -> None:
    command = ['zpool', 'create', name]
    if raid_type != 'stripe':
        command.append(raid_type)
    command.extend(disks)
    run_command(command, module, f"Failed to create zpool '{name}'")

def create_volume(name: str, size: str, module: AnsibleModule) -> None:
    command = ['zfs', 'create', '-V', size, name]
    run_command(command, module, f"Failed to create volume '{name}' of size '{size}'")

def destroy_zpool(name: str, module: AnsibleModule) -> None:
    run_command(['zpool', 'destroy', name], module, f"Failed to destroy zpool '{name}'")

def destroy_volume(name: str, module: AnsibleModule) -> None:
    run_command(['zfs', 'destroy', name], module, f"Failed to destroy volume '{name}'")

def set_zpool_options(name: str, options: List[str], module: AnsibleModule) -> None:
    for option in options:
        command = ['zfs', 'set', option, name]
        run_command(command, module, f"Failed to set option '{option}' on zpool '{name}'")

def check_zpool_exists(name: str) -> bool:
    try:
        subprocess.run(['zpool', 'list', name], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def check_volume_exists(name: str) -> bool:
    try:
        subprocess.run(['zfs', 'list', name], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def validate_raid_disks(raid_type: str, disks: List[str], module: AnsibleModule) -> None:
    raid_min_disks = {
        'stripe': 1,
        'mirror': 2,
        'raidz': 3,
        'raidz1': 3,
        'raidz2': 4,
        'raidz3': 5,
    }

    if raid_type == 'raidz1':
        raid_type = 'raidz'

    min_disks = raid_min_disks.get(raid_type)
    if min_disks is None:
        module.fail_json(msg=f"Invalid RAID type '{raid_type}'. Valid types are: {', '.join(raid_min_disks.keys())}")

    if len(disks) < min_disks:
        module.fail_json(
            msg=f"RAID type '{raid_type}' requires at least {min_disks} disks. "
                f"Provided disks: {len(disks)} ({disks})"
        )

def cache_device_exists(zpool: str, device: str) -> bool:
    try:
        result = subprocess.run(
            ['zpool', 'status', zpool],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        return f"cache" in result.stdout and device in result.stdout
    except subprocess.CalledProcessError:
        return False

def add_cache_to_zpool(zpool: str, device: str, module: AnsibleModule) -> None:
    command = ['zpool', 'add', zpool, 'cache', device]
    run_command(command, module, f"Failed to add cache device '{device}' to zpool '{zpool}'")

def hotspare_exists(zpool: str, device: str) -> bool:
    try:
        result = subprocess.run(
            ['zpool', 'status', zpool],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        return 'spares' in result.stdout and device in result.stdout
    except subprocess.CalledProcessError:
        return False

def add_hotspare(zpool: str, device: str, module: AnsibleModule) -> None:
    command = ['zpool', 'add', zpool, 'spare', device]
    run_command(command, module, f"Failed to add hot spare '{device}' to zpool '{zpool}'")

def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        type=dict(type='str', choices=['zpool', 'volume', 'cache'], default='zpool'),
        size=dict(type='str', required=False),
        zpool=dict(type='str', required=False),
        raidz=dict(type='str', default='stripe'),
        disks=dict(type='list', elements='str', default=[]),
        hot_spare=dict(type='list', elements='str', required=False, default=[]),
        compression=dict(type='bool', default=False),
        canmount=dict(type='bool', default=False),
        state=dict(type='str', choices=['present', 'absent'], default='present'),
    )

    result = dict(changed=False)
    module = AnsibleModule(argument_spec=module_args,supports_check_mode=False)

    name = module.params['name']
    obj_type = module.params['type']
    state = module.params['state']
    compression = 'compression=on' if module.params['compression'] else 'compression=off'
    canmount = 'canmount=on' if module.params['canmount'] else 'canmount=off'
    options = [compression, canmount]

    changed = False

    # Handle zpool creation/deletion
    if obj_type == 'zpool':
        pool_exists = check_zpool_exists(name)

        if state == 'present':
            if not pool_exists and module.params['hot_spare'] and not module.params['disks']:
                module.fail_json(msg=f"Cannot create zpool '{name}' with hot spares but without disks.")

            if not pool_exists:
                validate_raid_disks(module.params['raidz'], module.params['disks'], module)
                create_zpool(name, module.params['raidz'], module.params['disks'], module)
                changed = True

            option_changed = set_zpool_options(name, options, module)
            if option_changed:
                changed = True

            for spare in module.params['hot_spare']:
                if not hotspare_exists(name, spare):
                    add_hotspare(name, spare, module)
                    changed = True

            result['changed'] = changed
            module.exit_json(**result)

        elif state == 'absent':
            if pool_exists:
                if module.check_mode:
                    module.exit_json(changed=True, msg=f"Would destroy zpool '{name}' (check mode).")
                destroy_zpool(name, module)
                result['changed'] = True
            module.exit_json(**result)

    # Handle volume creation/deletion
    elif obj_type == 'volume':
        if not module.params['size']:
            module.fail_json(msg="'size' is required when type is 'volume'")
        
        volume_exists = check_volume_exists(name)

        if state == 'present':
            if volume_exists:
                if module.check_mode:
                    module.exit_json(changed=False, msg=f"Volume '{name}' already exists (check mode).")
                set_zpool_options(name, options, module)
                module.exit_json(changed=False, msg=f"Volume '{name}' exists. Options updated if necessary.")
            else:
                if module.check_mode:
                    module.exit_json(changed=True, msg=f"Would create volume '{name}' (check mode).")
                create_volume(name, module.params['size'], module)
                set_zpool_options(name, options, module)
                result['changed'] = True
                module.exit_json(**result)

        elif state == 'absent':
            if volume_exists:
                if module.check_mode:
                    module.exit_json(changed=True, msg=f"Would destroy volume '{name}' (check mode).")
                destroy_volume(name, module)
                result['changed'] = True
            module.exit_json(**result)

    if obj_type == 'cache':
        if not module.params['size'] or not module.params['zpool']:
            module.fail_json(msg="'size' and 'zpool' are required when type is 'cache'")

        zvol_name = module.params['name']
        size = module.params['size']
        zpool = module.params['zpool']

        volume_exists = check_volume_exists(zvol_name)

        if not volume_exists:
            if module.check_mode:
                module.exit_json(changed=True, msg=f"Would create cache volume '{zvol_name}' (check mode).")
            create_volume(zvol_name, size, module)
            changed = True

        if not cache_device_exists(zpool, f"/dev/zvol/{zvol_name}"):
            if module.check_mode:
                module.exit_json(changed=True, msg=f"Would add cache device '/dev/zvol/{zvol_name}' to zpool '{zpool}' (check mode).")
            add_cache_to_zpool(zpool, f"/dev/zvol/{zvol_name}", module)
            changed = True

        module.exit_json(changed=changed, msg=f"Cache device '{zvol_name}' ensured in zpool '{zpool}'")


def main():
    run_module()

if __name__ == '__main__':

    main()
