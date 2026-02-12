WHAT: 
- The purpose of our business is to provide baremetal server hosting services
- We handle
    - Procurement exclusively of HPE and Dell servers
    - Receiving
    - Physical installation in server rack
    - Cabling in rack to top of rack switches
    - Documenting installation in DCIM which is NetBox
    - Provisioning server to vendor tools like HPE oneview and Dell OpenManage
    - Apply ansible playbooks for hardening the BMC, no OS is installed
    - Deliver server to client via email or web portal with details of their order
    - Manage lifecycle of server, firmware updates
    - Track server usage via redfish API and log to a timeseries database such a prometheus
    - Have a portal where usage is displayed for each tenant of all their server assets
    - Track vendor warranty status
    - Deal with any hardware failures via our monitoring system and track repair tickets
    - Decomission of evergreen infrastructure with integrated consolidation calculator for tenant
    -I have 5 datacenters in 5 different cities each datacenter has an onsite tech

    - Tools used currently
        - Netbox
        - Prometheus
        - Grafana
        - Vendor tools
            - HPE OneView
            - Dell OpenManage
        - Canonical MaaS
        - Jira
        - ansible

MISSION

Be able to have an integrated automated process to deploy a server in every step, potentially using an ESB to link all the tools and automate all the processes, when an order is received in the tenant portal, it will check existing inventory for requested configuration, if the server is not in stock it will trigger a quote request to both vendors HPE and Dell, once quotes are received and conpared they will be approved and the order will be put to the selected ventor,
order delivery will be tracked, once received the tech will mark the goods as received in the database and he will rack the server and connect the network cables to the rack main switches and management switches, we will receive the server order manifest from the manufacturer with the MAC address of the BMC, when server is powered on the DHCP server will see the BMC request and IP and it will trigger a api call to netbox to see if it exists, if it does it will trasition it's
state to checking physical config, it will pxe boot an linux image and check switch connectivity with lldp, then it will update port assignments in netbox, once server is online it will be put in a staging netbox account, it will be provisioned to the respective vendor tools like oneview or openmanage then latest firmware updates have to be applied and hardening profiles have to be run via ansible, server now becomes in ready state and can be transfered to a tenant account, the
tenant is notified of is order complete and it can consume the servers, then we track cpu usage via redfish api and log it to prometheus and can report this back via a web UI to the tenant, we track server warranty status and we already monitor hardware and automatically open tickets in jira on failure, when the server ages we propose our tenant a refresh strategy based on usage and consolidation factors.

Dont make any code just plan a high level strategy for implenting this as efficiently as possible, tools can be added, then we will breakdown each step into a process that can be mapped to something maybe triggers on the ESB
