"""About 500 big and medium employers in the UK that hold a Home Office sponsor licence (Skilled Worker).
Tailor&Track finds each one's careers site once (Find careers sites, in Collection settings) and adds the
ones it can read to the company boards. Edit freely: one company per line, section titles start with #.
"""
VERSION = "2026-11-03a"   # all Tailor&Track files must have the same version

UK_EMPLOYERS_TEXT = """
# Banks, payments, fintech
Barclays
HSBC
Lloyds Banking Group
NatWest Group
Santander UK
Standard Chartered
Nationwide Building Society
Virgin Money
Metro Bank
TSB Bank
Monzo
Starling Bank
Revolut
Wise
Checkout.com
GoCardless
Funding Circle
Zopa
OakNorth
Atom Bank
ClearScore
Tide
Lendable
Paddle
Ebury
Paysafe
Thought Machine
10x Banking
Mambu
Klarna
Stripe
PayPal
Visa
Mastercard
American Express
Capital One
Worldpay
Fiserv
FIS
Global Payments
Adyen
Moneybox
Curve
Marshmallow
Zego
Cleo
Kroo
Chip
Plum
Freetrade
Trading 212
IG Group
CMC Markets
Plus500
Hargreaves Lansdown
AJ Bell
St. James's Place
Rathbones
Schroders
abrdn
M&G
Jupiter
Fidelity International
Vanguard
BlackRock
Invesco
LSEG
Experian
Equifax
TransUnion
Moody's
S&P Global
Fitch Ratings
MSCI
Bloomberg
# Investment banks and insurers
Goldman Sachs
J.P. Morgan
Morgan Stanley
Citi
Bank of America
Deutsche Bank
BNP Paribas
Societe Generale
UBS
Nomura
Mizuho
MUFG
Jefferies
Macquarie
Barclays Investment Bank
Legal & General
Aviva
Prudential
Phoenix Group
Hiscox
Beazley
Admiral Group
Direct Line Group
Allianz
AXA
Zurich
Aon
Marsh McLennan
WTW
Gallagher
Lloyd's of London
QBE
Chubb
AIG
Markel
Brit Insurance
Canopius
# Consulting, accounting, IT services
Deloitte
PwC
EY
KPMG
Accenture
Capgemini
Cognizant
Infosys
Tata Consultancy Services
Wipro
HCLTech
Tech Mahindra
LTIMindtree
Mphasis
Hexaware
Persistent Systems
Coforge
IBM
CGI
Atos
Sopra Steria
NTT Data
DXC Technology
Kyndryl
Kainos
Version 1
BJSS
Endava
EPAM
Thoughtworks
Slalom
Globant
Publicis Sapient
McKinsey & Company
Boston Consulting Group
Bain & Company
Oliver Wyman
PA Consulting
Baringa
Grant Thornton
BDO
Forvis Mazars
RSM
Alvarez & Marsal
FTI Consulting
Gartner
Genpact
Concentrix
Teleperformance
Capita
Serco
Sodexo
Mitie
ISS
Compass Group
Kier
Balfour Beatty
Arup
AECOM
Jacobs
WSP
AtkinsRealis
Mott MacDonald
Ricardo
Turner & Townsend
Gleeds
Mace
Laing O'Rourke
Costain
Morgan Sindall
# Defence, aerospace, engineering, manufacturing
BAE Systems
Babcock
Leonardo
Thales
QinetiQ
Rolls-Royce
GKN Aerospace
Airbus
Boeing
Lockheed Martin
Raytheon
MBDA
Siemens
Siemens Energy
GE Vernova
GE Aerospace
ABB
Schneider Electric
Honeywell
Johnson Controls
JCB
Jaguar Land Rover
Nissan
Toyota
BMW Group
Bentley Motors
Aston Martin
McLaren
Rolls-Royce Motor Cars
Ford
Stellantis
Dyson
Renishaw
Spirax Group
Smiths Group
Halma
Weir Group
IMI
Rotork
Oxford Instruments
Spectris
Johnson Matthey
Croda
Ineos
Tate & Lyle
# Technology, software, internet
Google
Microsoft
Amazon
Meta
Apple
Oracle
Salesforce
SAP
Adobe
Cisco
Dell Technologies
HP
Hewlett Packard Enterprise
Intel
Arm
NVIDIA
Qualcomm
AMD
Google DeepMind
Darktrace
Sage
Ocado Group
Deliveroo
Just Eat Takeaway
Skyscanner
Trainline
Rightmove
Auto Trader
Moneysupermarket
Zoopla
ASOS
Boohoo
THG
Farfetch
Depop
Gymshark
Bumble
Snyk
Improbable
Octopus Energy
Kraken Technologies
OVO
Cera
Signal AI
Entrust
Featurespace
Quantexa
Synthesia
Wayve
Faculty
Stability AI
Bloom & Wild
Papier
Gousto
HelloFresh
Multiverse
Beamery
Pleo
Unity
Rockstar Games
Sony Interactive Entertainment
Electronic Arts
Ubisoft
King
Sky
BT Group
Vodafone
Virgin Media O2
Three UK
BBC
ITV
Channel 4
Spotify
Netflix
Thomson Reuters
Pearson
RELX
Informa
Wolters Kluwer
Autodesk
Atlassian
Workday
ServiceNow
Snowflake
Databricks
MongoDB
Elastic
Datadog
Cloudflare
Palantir
Booking.com
Expedia Group
Uber
Bolt
Indeed
LinkedIn
Canva
Figma
Miro
Intercom
Zendesk
HubSpot
Twilio
Okta
CrowdStrike
Palo Alto Networks
Fortinet
Zscaler
Sophos
NCC Group
Netcompany
Softcat
Computacenter
Bytes Technology
Kin + Carta
Made Tech
Equal Experts
Infinity Works
Ensono
Rackspace
Claranet
Six Degrees
Node4
Pax8
Iress
FNZ
SS&C
Broadridge
Temenos
Finastra
Calastone
Clearwater Analytics
Marshall Wace
Man Group
Winton
G-Research
Jane Street
Citadel
Optiver
IMC Trading
Jump Trading
Hudson River Trading
Two Sigma
DRW
Tower Research Capital
XTX Markets
Squarepoint Capital
Millennium
Balyasny
Point72
# Pharma, life sciences, healthcare
GSK
AstraZeneca
Pfizer
Novartis
Roche
Sanofi
MSD
Johnson & Johnson
Bayer
Novo Nordisk
Eli Lilly
AbbVie
Amgen
Takeda
Boehringer Ingelheim
Bristol Myers Squibb
Smith & Nephew
Haleon
Reckitt
Abcam
Oxford Nanopore
Illumina
Thermo Fisher Scientific
IQVIA
ICON
Parexel
Syneos Health
Fortrea
Labcorp
Medpace
PPD
Charles River Laboratories
Bupa
HCA Healthcare UK
Spire Healthcare
Circle Health Group
Ramsay Health Care
Nuffield Health
Boots
Philips
GE HealthCare
Siemens Healthineers
Medtronic
Stryker
BD
Abbott
# Retail, consumer, food, hospitality
Tesco
Sainsbury's
Asda
Morrisons
John Lewis Partnership
Marks & Spencer
Next
Primark
Kingfisher
Dunelm
Currys
JD Sports
Frasers Group
Burberry
Diageo
Unilever
Nestle
PepsiCo
Coca-Cola Europacific Partners
Mondelez
Heineken
AB InBev
Britvic
Whitbread
IHG Hotels & Resorts
Hilton
Marriott
Greene King
Mitchells & Butlers
Pret A Manger
Costa Coffee
IKEA
H&M
Inditex
Aldi
Lidl
Iceland Foods
B&M
Pets at Home
Holland & Barrett
Superdry
Matalan
Selfridges
Harrods
Mulberry
Associated British Foods
Greggs
Domino's Pizza Group
Nando's
Wagamama
Hollywood Bowl
# Energy, utilities, transport, logistics
BP
Shell
Centrica
National Grid
SSE
ScottishPower
EDF
E.ON
RWE
Orsted
Thames Water
Severn Trent
United Utilities
Anglian Water
Yorkshire Water
Northumbrian Water
UK Power Networks
Network Rail
Transport for London
HS2
Heathrow
Gatwick
Manchester Airports Group
British Airways
easyJet
Virgin Atlantic
Jet2
TUI
Eurostar
FirstGroup
Go-Ahead Group
Arriva
Stagecoach
Maersk
DHL
DPD
Royal Mail
Evri
Wincanton
GXO
Kuehne+Nagel
DSV
Ceva Logistics
Uniserve
# Media, advertising, publishing
WPP
Publicis Groupe
Omnicom
Dentsu
Havas
Interpublic Group
The Economist Group
Financial Times
News UK
Guardian Media Group
Reach
Future
Bauer Media
Global
Penguin Random House
HarperCollins
Hachette UK
Oxford University Press
Cambridge University Press & Assessment
# Universities
University of Oxford
University of Cambridge
Imperial College London
University College London
King's College London
London School of Economics
University of Edinburgh
University of Manchester
University of Bristol
University of Warwick
University of Glasgow
University of Leeds
University of Birmingham
University of Southampton
University of Nottingham
University of Sheffield
Queen Mary University of London
Durham University
Newcastle University
Cardiff University
# Law firms
A&O Shearman
Clifford Chance
Linklaters
Freshfields
Slaughter and May
Herbert Smith Freehills
DLA Piper
CMS
Eversheds Sutherland
Pinsent Masons
Hogan Lovells
Norton Rose Fulbright
Baker McKenzie
Ashurst
Bird & Bird
# Recruitment agencies (many post client jobs that sponsor)
Hays
PageGroup
Robert Walters
Robert Half
Randstad
Adecco
ManpowerGroup
Harvey Nash
Reed
Hudson
Morgan McKinley
Kelly Services
SThree
Impellam
Gattaca
Sanderson
La Fosse
Lorien
Experis
Michael Page
Spencer Ogden
Nigel Frank International
Frank Recruitment Group
Tenth Revolution Group
Hyper Recruitment Solutions
Cpl
Hunter Bond
Oliver Bernard
Understanding Recruitment
Harnham
Investigo
Goodman Masson
Phaidon International
Selby Jennings
Ventula Consulting
"""


def employers():
    """[(sector, company name)] from the list above."""
    out, sector = [], ""
    for line in UK_EMPLOYERS_TEXT.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            sector = line.lstrip("# ").strip()
            continue
        out.append((sector, line))
    seen, uniq = set(), []
    for s, n in out:
        if n.lower() not in seen:
            seen.add(n.lower())
            uniq.append((s, n))
    return uniq