"""Who-Is from 192.168.100.11 on 47808: the simulated devices and the Niagara station (device 2001) should all answer."""
import asyncio
import BAC0

async def main():
    BAC0.log_level('error')
    async with BAC0.start(ip='192.168.100.11/24', port=47808) as bac:
        found = await bac.who_is()
        ids = sorted(int(str(i.iAmDeviceIdentifier[1])) for i in found)
        print(len(ids), 'answered; Niagara (2001) among them:', 2001 in ids)
        if 2001 in ids:
            print('  Niagara device:', await bac.read('192.168.100.228 device 2001 objectName'), '|',
                  await bac.read('192.168.100.228 device 2001 vendorName'), '|', await bac.read('192.168.100.228 device 2001 modelName'))
asyncio.run(main())
