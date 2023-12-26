import csv, re, argparse, sys
from io import SEEK_SET
from curses.ascii import isalnum
from decimal import Decimal

# district numeral offset in name, must be changed if name structure changes
DN_OFF = 2

# valid district numerals for SM
valid_districts = (0, 1, 2, 3, 4, 5, 6, 7)

# set up and argument parser and help system
parser = argparse.ArgumentParser(
                    prog=sys.argv[0],
                    description='Convert "repeaters.csv" from SSA / SK6BA repeater database to OpenGD77 CPS compatible csv import files',
                    epilog='Please email sa0asm@fastmail.se with feedback or suggestions!')
parser.add_argument('filename', action='store', help='Input file in SK6BA "repeaters.csv" format. (See https://www.ssa.se/vushf/repeatrar-fyrar/)')
parser.add_argument('--custom', action='store', type=str, metavar='filename',
                     help='Optional file in OpenGD77 CPS "Channels.csv" format (without the header row) to add to output. ' +
                     'File must use semicolon (";") characters as field delimiter and Channel Numbers must be < 500.')
parser.add_argument('--output', action='store', type=str, metavar='path', default='.',
                     help='Path to directory where the OpenGD77 CPS .csv output files will be stored, defaults to "."')
parser.add_argument('--allskip', action='append', type=int, metavar='district',
                     help='Repeaters in the district will have the "All Skip" flag set. Argument can stack to indicate multiple districts.')
parser.add_argument('--home', action='store', type=int, metavar='district',
                     help='Indicating "home" district by number will turn on "All Skip" flag for repeaters in all other districts. Mutually exclusive to --allskip argument.')

# parse and validate arguments
args = parser.parse_args()
if args.allskip:
    for skip in args.allskip:
        if skip not in valid_districts:
            print('{}: error: invalid district number {} in --allskip argument!'.format(sys.argv[0], skip))
            sys.exit()
    if args.home:
        print('{}: error: --home and --allskip arguments are mutually exclusive!'.format(sys.argv[0]))
        sys.exit()

if args.home and args.home not in valid_districts:
        print('{}: error: invalid district number {} in --home argument!'.format(sys.argv[0], args.home))
        sys.exit()

# create Channels.csv file for import into OpenGD77 CPS
with open(args.output + '/Channels.csv', 'w') as outfile:

    # OpenGD77 CPS Channel.csv field names 
    fieldnames = ['Channel Number', 'Channel Name', 'Channel Type', 'Rx Frequency',
                 'Tx Frequency', 'Bandwidth (kHz)', 'Colour Code', 'Timeslot', 'Contact',
                 'TG List', 'DMR ID', 'TS1_TA_Tx', 'TS2_TA_Tx ID', 'RX Tone', 'TX Tone',
                 'Squelch', 'Power', 'Rx Only', 'Zone Skip', 'All Skip', 'TOT', 'VOX',
                 'No Beep', 'No Eco', 'APRS', 'Latitude', 'Longitude']

    # write csv header to output file
    writer = csv.DictWriter(outfile, fieldnames, delimiter=';')
    writer.writeheader()

    # add manually configured channels (id < 500) to output file
    if args.custom:
        with open(args.custom, 'r') as custfile:
            for row in csv.DictReader(custfile, fieldnames, delimiter=';'):
                name = row['Channel Name']
                if int(row['Channel Number']) > 499:
                    print('Warning: Channel number is 500 or greater for custom channel "{}"!'.format(name))
                row['Channel Name'] = name[:16].strip()
                writer.writerow(row)

    # read channels from SSA repeater database
    channels = dict() 
    with open(args.filename, 'r') as rptfile:
        for row in csv.DictReader(rptfile):

            # only process QRV repeaters from single-digit districts
            if len(row['district']) == 1 and 'Repeater' in row['type'] and 'QRV' in row['status']:
            
                # only process FM and DRM repeaters on 2m/70cm
                if ('DMR' in row['mode'] or 'FM' in row['mode']) and (row['band'] == '2' or row['band'] == '70'):
                    channel = dict()

                    # fix zeros in callsigns
                    callsign = row['call'].replace('Ø','0')

                    # remove ancillary suffix from callsign
                    if '/' in callsign:
                        callsign = callsign[:callsign.find('/')]
                    if '-' in callsign:
                        callsign = callsign[:callsign.find('-')]

                    # abbreviate city names
                    city = row['city'].strip()
                    if ' /' in city: city = city[:city.find(' /')]
                    city = city.replace('Upplands ', 'U.')

                    # create name from callsign, location city and band
                    band = '2m' if '2' in row['band'] else '70cm'
                    name = str(callsign + ' ' + city + ' ' + band)[:16].strip()

                    # validate district numeral in callsign
                    district = name[DN_OFF]
                    if not district.isnumeric() or int(district) not in valid_districts:
                        print('Warning: district number {} in "{}" is not valid!'.format(district, name))
                    district = int(row['district'])

                    # prefer to use repeater in DMR mode
                    channel['Channel Type'] = 'Digital' if 'DMR' in row['mode'] else 'Analogue'

                    # calculate input/output frequencies 
                    channel['Rx Frequency'] = row['output']
                    offset = Decimal(row['tx_shift']) if row['tx_shift'].replace('.','').replace('-','').isnumeric() else 0
                    channel['Tx Frequency'] = '{0}'.format(Decimal(row['output']) + offset)

                    # DMR specific fields
                    if channel['Channel Type'] == 'Digital':

                        cc_idx = row['access'].find('CC')
                        if cc_idx != -1:
                            channel['Colour Code'] = row['access'][cc_idx+3:cc_idx+5]

                            channel['Timeslot'] = 1

                            net = row['network'] if 'BM' not in row['network'] else 'Brandmeister'
                            channel['TG List'] = net if not 'Brandmeister' in net else 'Brandmeister'

                            channel['DMR ID'] = 'None'
                            channel['TS1_TA_Tx'] = 'Off'
                            channel['TS2_TA_Tx ID'] = 'Off'

                    # analogue channel fields
                    else:
                        channel['Bandwidth (kHz)'] = '12.5'
                        
                        tone_pattern = re.compile('([0-9]+\.[0-9])')
                        tone_match = tone_pattern.search(row['access'])
                        tone = '' if tone_match == None else tone_match.group()
                        channel['RX Tone'] = tone
                        channel['TX Tone'] = tone
                        channel['Squelch'] = 'Disabled'

                    channel['Power'] = 'Master'
                    channel['Rx Only'] = 'No'
                    channel['Zone Skip'] = 'No'

                    # calculate if we should set the "All Skip" flag for this repeater
                    all_skip = (args.home != None and district != args.home) or (args.allskip and district in args.allskip)

                    channel['All Skip'] = 'Yes' if all_skip else 'No' 
                    channel['TOT'] = '0'
                    channel['VOX'] = 'Off'
                    channel['No Beep'] = 'No'
                    channel['No Eco'] = 'No'
                    channel['APRS'] = 'None'

                    channel['Latitude'] = row['lat'].replace('.',',')
                    channel['Longitude'] = row['lng'].replace('.',',')

                    # make sure channel name is unique as OpenGD77 CPS doesn't like duplicate names
                    while name in channels:
                        mode = 'DMR' if channel['Channel Type'] == 'Digital' else 'FM'

                        # if we have duplicates, try removing band
                        if ' 7' in name or ' 2' in name[10:]:
                            name = name[:name.rfind(' ')]

                        # or try appending mode if there's room
                        elif len(name) < 15:
                            name = str(name + ' ' + mode)[:16]
                        elif len(name) < 16:
                            name = name + 'A' if mode == 'FM' else name + 'D'

                        # try underscores instead of spaces
                        elif ' ' in name:
                            name = name.replace(' ', '_', 1)

                        # try dots instead of underscores
                        elif '_' in name:
                            name = name.replace('_', '.', 1)
                        
                        # try dashes instead of dots
                        elif '.' in name:
                            name = name.replace('.', '-', 1)
                        
                        # try slashes instead of dashes
                        elif '-' in name:
                            name = name.replace('-', '/', 1)
                        
                        # if all else fails, shorten name by one
                        else:                                
                            print('Forced to shorten name "{}" to "{}"!'.format(name, name[:-2].strip()))
                            name = name[:-2].strip()

                    # save the channel in dict
                    channels[name] = channel

    # output channels sorted by type, callsign digit and frequency 
    id = 500
    for channel in sorted(channels.items(), key=lambda c: (c[1]['Channel Type'], c[0][DN_OFF], Decimal(c[1]['Rx Frequency']))):
        name = channel[0]
        data = channel[1]
        id = id + 1
        data['Channel Number'] = id
        data['Channel Name'] = name
        writer.writerow(data)

# create Zones to be populated with channels
zones = dict()
zones['All 2m DMR'] = list()
zones['All 70cm DMR'] = list()
for district in valid_districts:
    zones['SM{} All Channels'.format(district)] = list()
    zones['SM{} Analogue'.format(district)] = list()
    zones['SM{} DMR'.format(district)] = list()

# read the newly created file to automatically populate Zones
with open(args.output + '/Channels.csv', 'r') as chanfile:
        for row in csv.DictReader(chanfile, dialect='excel', delimiter=';'):

            name = row['Channel Name'].strip()
            district = name[DN_OFF]
            mode = 'DMR' if 'Digital' in row['Channel Type'] else 'Analogue'

            # only add channels named with district numerals to Zones
            if district.isnumeric():

                zones['SM{} {}'.format(district, mode)].append(name)
                zones['SM{} All Channels'.format(district)].append(name)
                if len(zones['SM{} All Channels'.format(district)]) > 80:
                    print('Warning: Zone "SM{} All Channels" has more than 80 entries!'.format(district))

                if mode == 'DMR':
                    if row['Rx Frequency'][0] == '1':
                        zones['All 2m DMR'].append(name)
                        if len(zones['All 2m DMR']) > 80:
                            print('Warning: Zone "All 2m DMR" has more than 80 entries!')
                    if row['Rx Frequency'][0] == '4':
                        zones['All 70cm DMR'].append(name)
                        if len(zones['All 70cm DMR']) > 80:
                            print('Warning: Zone "All 70cm DMR" has more than 80 entries!')

# write Zones.csv file for import into OpenGD77 CPS
with open(args.output + '/Zones.csv', 'w') as outfile:

    # OpenGD77 CPS Zones.csv field names 
    fieldnames = ['Zone Name']
    for n in range(1,81):
        fieldnames.append('Channel{}'.format(n))

    # write csv header to output file
    writer = csv.DictWriter(outfile, fieldnames, delimiter=';')
    writer.writeheader()

    # write zones to csv file
    for name in zones.keys():
        data = zones[name]
        if len(data) > 0:
            data.insert(0, name)
            outfile.write(';'.join(data))
            outfile.write(';' * (81 - len(data)))
            outfile.write('\r\n')
