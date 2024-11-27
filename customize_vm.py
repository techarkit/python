#!/usr/bin/python
from ansible.module_utils.basic import AnsibleModule
import VI  # Ensure pyVmomi is installed
from VIServer import VIServer

def main():
    module = AnsibleModule(
        argument_spec=dict(
            host=dict(required=True),
            user=dict(required=True),
            password=dict(required=True),
            target_vm=dict(required=True),
            ip_address=dict(required=True),
            netmask=dict(required=True),
            domain=dict(required=True),
        ),
        supports_check_mode=False
    )
    host = module.params['host']
    user = module.params['user']
    password = module.params['password']
    target_vm = module.params['target_vm']
    ip_address = module.params['ip_address']
    netmask = module.params['netmask']
    domain = module.params['domain']

    try:
        server = VIServer()
        server.connect(host, user, password)
        vm_obj = server.get_vm_by_name(target_vm)

        request = VI.CustomizeVM_TaskRequestMsg()
        _this = request.new__this(vm_obj._mor)
        _this.set_attribute_type(vm_obj._mor.get_attribute_type())
        request.set_element__this(_this)

        spec = request.new_spec()
        globalIPSettings = spec.new_globalIPSettings()
        spec.set_element_globalIPSettings(globalIPSettings)

        nicSetting = spec.new_nicSettingMap()
        adapter = nicSetting.new_adapter()
        fixedip = VI.ns0.CustomizationFixedIp_Def("ipAddress").pyclass()
        fixedip.set_element_ipAddress(ip_address)
        adapter.set_element_ip(fixedip)
        adapter.set_element_subnetMask(netmask)
        nicSetting.set_element_adapter(adapter)
        spec.set_element_nicSettingMap([nicSetting])

        identity = VI.ns0.CustomizationLinuxPrep_Def("identity").pyclass()
        identity.set_element_domain(domain)
        hostName = VI.ns0.CustomizationFixedName_Def("hostName").pyclass()
        hostName.set_element_name(target_vm.replace("_", ""))
        identity.set_element_hostName(hostName)
        spec.set_element_identity(identity)

        request.set_element_spec(spec)
        task = server._proxy.CustomizeVM_Task(request)._returnval
        vi_task = VITask(task, server)
        status = vi_task.wait_for_state([vi_task.STATE_SUCCESS, vi_task.STATE_ERROR], 300)

        if status == vi_task.STATE_SUCCESS:
            module.exit_json(changed=True, msg="Customization successful.")
        else:
            module.fail_json(msg="Customization failed.")

    except Exception as e:
        module.fail_json(msg=f"Error: {str(e)}")

if __name__ == '__main__':
    main()
