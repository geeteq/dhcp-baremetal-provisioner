Phases in project and deliverables
- Phase 0: reset server to initial state

- Phase one 1: Initial racking of server and power-on
    - Initital state the server is racked and powered-on and connnected to the standard configuration
    - 
    - We assume the server is physically connected to:
        - server1 - bmc nic - management switch
        - server1 - management nic - management switch
        - server1 - prod nic1 - top of rack switch 1
        - server1 - prod nic2 - top of rack switch 2
    
    - Simulate fake dhcp request for device CENT-SRV-035 in NetBox 
    - Set the ip to 10.22.4.202 
    - The NIC must exist with MAC: A0:36:9F:77:05:00 and no IP use this ip: 10.22.4.202
    - If the NIC doesnt exists, log an error condition
    - If update fails log an error condition
    - Else update the IP in NetBox on the BMC interace and log the event
    - Change the server sate to from Offline to Planned
    - No other interface should be defined at this point, if they are they will be validated later

There must be a shell script that initiates the test phase 1

Make a simple web ui with a line and a dot for each server with all the ESB event_types a kind of timeline, each dot on the line has a heading with the state name that let's you monitor where the process is, the web page is synchronous, it polls and updates the state as it moves, i don't know where to get this information, maybe redis directly? the web page should have a list of all processes in the redis queue and a timeline for each


- Phase two:


