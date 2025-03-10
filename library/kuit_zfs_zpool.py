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
    state:
            -   present
            -   absent
            -   export
            -   import
        required: false
        type: str
    type:
            -   stripe
            -   mirror
            -   raidz
            -   raidz2
            -   raidz3
        required: false
        type: str
    disks:
        description: List of disks
        required: true
        type: str
    compression:
            -   true
            -   false
        required: false
        type: bool
    canmount:
            -   true
            -   false
        required: false
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
from subprocess import PIPE
import time
from ansible.module_utils.basic import AnsibleModule


def run_module():
    module_args = dict(
        name=dict(type='str', required=True),
        type=dict(type='str', default='stripe'),
        disks=dict(type='list', default=[]),
        compression=dict(type='str', default='off'),
        canmount=dict(type='str', default='off'),
        state=dict(type='str', default='present'),
        directory=dict(type='str')
    )

    result = dict(
        changed=False,
        original_message='',
        message='',
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False
    )


    if module.params['state'] == 'present':
        if module.params["compression"] == 'True': compress = "on"
        else: compress = "off"
        if module.params["canmount"] == 'True': mount = "on"
        else: mount = "off"
        options = [f'compression={compress}', f'canmount={mount}']
        if not check_for_zpool(module.params['name']): 
            if module.check_mode:
                module.exit_json(changed=True, msg="Would create {}".format(module.params['name']))


            if module.params['type'] == 'stripe':
                rc1 = create_zpool(module.params['name'],module.params['disks'])
                rc2 = set_zpool_option(module.params['name'],options)
            else:
                rc1 = create_zpool(module.params['name'],module.params['type'],module.params['disks'])
                rc2 = set_zpool_option(module.params['name'],options)
            change_state(rc1 and rc2, result,module)

        else:
            if module.check_mode:
                module.exit_json(changed=False, msg="Exist {}".format(module.params['name']))

            rc = set_zpool_option(module.params['name'],options)
            change_state(rc, result,module)

    if module.params['state'] == 'absent':
        
        if check_for_zpool(module.params['name']):
            if module.check_mode:
                module.exit_json(changed=True, msg="Would delete {}".format(module.params['name']))

            rc = destroy_zpool(module.params['name'])
            change_state(rc, result,module)
        else:
            if module.check_mode:
                module.exit_json(changed=False, msg="Already absent {}".format(module.params['name']))

            module.fail_json(msg='Unable to destroy zpool. No such zpool', **result)

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

    module.exit_json(**result)

def create_zpool(*args):
    try:
        if isinstance(args[-1],list) and len(args) == 2:
            command = ['zpool', 'create', args[0]]
            command.extend(args[-1])
            subprocess.run(command, check=True)
            return True
        else:
            command = ['zpool', 'create', args[0]]
            command.append(args[1])
            command.extend(args[-1])
            subprocess.run(command, check=True)
            return True
    except subprocess.CalledProcessError:
        return False

def set_zpool_option(zpool,*options):
    try:
        command = ['zfs', 'set']
        for option in options:
            command.extend(option)
        command.append(zpool)
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def destroy_zpool(zpool):
    try:
        command = ['zpool', 'destroy']
        command.append(zpool)
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

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

def check_for_zpool(name):
    try:
        subprocess.run(['zpool', 'list', name], check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def change_state(bool,result,module):
    if bool:
        result['changed'] = True
    else:
        module.fail_json(msg='Unable to create zpool', **result)

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

def main():
    run_module()

if __name__ == '__main__':

    main()