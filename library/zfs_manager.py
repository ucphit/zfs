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

def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        type=dict(type='str', choices=['zpool', 'volume'], default='zpool'),
        size=dict(type='str', required=False),
        raidz=dict(type='str', default='stripe'),
        disks=dict(type='list', default=[]),
        compression=dict(type='str', default='off'),
        canmount=dict(type='str', default='off'),
        state=dict(type='str', default='present')')
    )

    result = dict(changed=False)
    module = AnsibleModule(argument_spec=module_args,supports_check_mode=True)

    name = module.params['name']
    obj_type = module.params['type']
    state = module.params['state']
    compression = 'compression=on' if module.params['compression'] else 'compression=off'
    canmount = 'canmount=on' if module.params['canmount'] else 'canmount=off'
    options = [compression, canmount]

    # Validate required params for volumes
    if obj_type == 'volume' and not module.params['size']:
        module.fail_json(msg="'size' is required when type is 'volume'")

    # Handle zpool creation/deletion
    if obj_type == 'zpool':
        pool_exists = check_zpool_exists(name)

        if state == 'present':
            if pool_exists:
                if module.check_mode:
                    module.exit_json(changed=False, msg=f"Zpool '{name}' already exists (check mode).")
                set_zpool_options(name, options, module)
                module.exit_json(changed=False, msg=f"Zpool '{name}' exists. Options updated if necessary.")
            else:
                if module.check_mode:
                    module.exit_json(changed=True, msg=f"Would create zpool '{name}' (check mode).")
                create_zpool(name, module.params['raidz'], module.params['disks'], module)
                set_zpool_options(name, options, module)
                result['changed'] = True
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


def main():
    run_module()

if __name__ == '__main__':

    main()
"""
    if module.params['state'] == 'import':
        if not check_for_zpool(module.params['name']):
            if module.params['directory']:
                rc = import_zpool(module.params['name'],module.params['directory'])
            else:
                rc = import_zpool(module.params['name'])
            change_state(rc, result,module)
        else:
            module.fail_json(msg='Unable to import zpool. No such zpool', **result)

    if module.params['state'] == 'export':
        if check_for_zpool(module.params['name']):
            rc = export_zpool(module.params['name'])
            timeout = 150
            check_interval = 10
            start_time = time.time()
            while time.time() - start_time < timeout:
                if zpool_ready_for_import(module.params['name']):
                    with open('/tmp/lustre_import', 'w') as file:
                        file.write("completed\n")
                    result['message'] = 'Ready for import.'
                    break
                time.sleep(check_interval)
            change_state(rc, result,module)
            
        else:
            if module.check_mode:
                module.exit_json(changed=False, msg="No zpool to export {}".format(module.params['name']))
            module.fail_json(msg='Unable to destroy zpool. No such zpool', **result)

    if module.params['state'] == 'check':
        rc = check_for_zpool(module.params['name'])
        if rc:
            result['message'] = True
        else:
            result['message'] = False
            #module.fail_json(msg='No such zpool', **result)

def export_zpool(zpool):
    try:
        command = ['zpool', 'export']
        command.append(zpool)
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def import_zpool(zpool,dir=''):
    try:
        if dir !='':
            command = ['zpool', 'import', '-d']
            command.append(dir)
            command.append(zpool)
            subprocess.run(command, check=True)
            return True
        else:
            command = ['zpool', 'import']
            command.append(zpool)
            subprocess.run(command, check=True)
            return True
    except subprocess.CalledProcessError:
        return False

def zpool_ready_for_import(pool_name):
    try:
        result = subprocess.run(['zpool', 'import'], stdout=PIPE, encoding='ascii')
        output = result.stdout

        if result.returncode != 0:
            return False

        if pool_name in output:
            return True
        else:
            return False

    except Exception as e:
        return False
"""