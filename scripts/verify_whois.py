"""Who-Is on 47808 (as Niagara does) from the address kept for Niagara, plus a drift check on RTU_1's first input."""
import asyncio, sys
import BAC0

async def main():
    BAC0.log_level('error')
    async with BAC0.start(ip=f'{sys.argv[1] if len(sys.argv) > 1 else "192.168.100.228"}/24', port=47808) as bac:
        found = await bac.who_is()
        print('Who-Is on 47808:', len(found), 'devices:', sorted(int(str(i.iAmDeviceIdentifier[1])) for i in found))
        objs = await bac.read('192.168.100.200 device 400001 objectList')
        ai = next(o for o in objs if 'analog-input' in str(o))
        name = await bac.read(f'192.168.100.200 analog-input {int(ai[1])} objectName')
        a = await bac.read(f'192.168.100.200 analog-input {int(ai[1])} presentValue')
        await asyncio.sleep(21)
        b = await bac.read(f'192.168.100.200 analog-input {int(ai[1])} presentValue')
        units = await bac.read(f'192.168.100.200 analog-input {int(ai[1])} units')
        print(f'RTU_1 {name} ({units}): {a} -> {b}')

asyncio.run(main())
