import asyncio, sys
import BAC0
async def main():
    BAC0.log_level('error')
    async with BAC0.start(ip='192.168.100.228/24', port=47808) as bac:
        inst = int(sys.argv[1])
        vals = []
        for _ in range(3):
            vals.append(await bac.read(f'192.168.100.204 analog-input {inst} presentValue'))
            await asyncio.sleep(11)
        print('VAV_1 ZN-T over 3 ticks:', vals, '| units', await bac.read(f'192.168.100.204 analog-input {inst} units'),
              '| vendor', await bac.read('192.168.100.204 device 300001 vendorName'), await bac.read('192.168.100.204 device 300001 modelName'))
asyncio.run(main())
