"""Seed metadata for the v1 crosswordese deck.

Clues are NOT stored here — they're scraped from crosswordheaven.com by
`scrape_clues.py` into `out/crossword_clues.json`. This file only carries
information that isn't already on the clue page: the canonical definition
of the answer + optional notes (etymology, variants, mnemonics).

Definitions are written to be short and verifiable against standard
dictionaries. Proper nouns are identified concretely.
"""
from __future__ import annotations

ENTRIES: list[dict] = [
    # ---------- 3-letter all-stars ----------
    {"answer": "ERA",  "category": "general",   "definition": "A period of time marked by distinctive character or events."},
    {"answer": "ORE",  "category": "general",   "definition": "Naturally occurring rock or mineral from which metal can be extracted."},
    {"answer": "ERE",  "category": "poetic",    "definition": "Before (archaic/poetic preposition or conjunction)."},
    {"answer": "ALE",  "category": "general",   "definition": "A type of beer brewed with top-fermenting yeast, traditionally English."},
    {"answer": "EAR",  "category": "general",   "definition": "The organ of hearing; also the seed-bearing head of a cereal plant."},
    {"answer": "ATE",  "category": "general",   "definition": "Past tense of 'eat'."},
    {"answer": "ELI",  "category": "names",     "definition": "Male given name; also Yale University nickname (after Elihu Yale).", "note": "Famous bearers: Eli Whitney, Eli Manning, Eli Wallach; biblical priest who mentored Samuel."},
    {"answer": "ALI",  "category": "names",     "definition": "Common Arabic given name; surname of boxer Muhammad Ali.", "note": "Also: Ali MacGraw (actress), Mahershala Ali (actor), Tatyana Ali."},
    {"answer": "AVE",  "category": "abbr",      "definition": "Latin greeting meaning 'hail'; also the abbreviation for 'avenue'."},
    {"answer": "OBI",  "category": "foreign",   "definition": "A wide sash tied around the waist of a Japanese kimono."},
    {"answer": "ETA",  "category": "abbr",      "definition": "Seventh letter of the Greek alphabet (H, η); also abbreviation for 'estimated time of arrival'."},
    {"answer": "UTE",  "category": "general",   "definition": "Member of a Native American people of the U.S. Southwest; also slang for utility vehicle/pickup."},
    {"answer": "EEL",  "category": "nature",    "definition": "Any of various elongated, snake-like fish (order Anguilliformes)."},
    {"answer": "ETE",  "category": "foreign",   "definition": "French for 'summer' (été)."},
    {"answer": "ION",  "category": "science",   "definition": "An atom or molecule with a net electric charge from gaining or losing electrons."},
    {"answer": "IRE",  "category": "general",   "definition": "Anger; wrath."},
    {"answer": "EMU",  "category": "nature",    "definition": "A large flightless Australian bird (Dromaius novaehollandiae), second-tallest living bird."},
    {"answer": "ONO",  "category": "names",     "definition": "Surname of Yoko Ono, Japanese-American multimedia artist and John Lennon's widow."},
    {"answer": "ENO",  "category": "names",     "definition": "Brian Eno, English musician and ambient-music pioneer, Roxy Music co-founder."},
    {"answer": "ESE",  "category": "abbr",      "definition": "East-southeast (compass direction); also a suffix denoting language/origin or jargon."},

    # ---------- 4-letter all-stars ----------
    {"answer": "OREO",  "category": "brand",        "definition": "Brand of chocolate sandwich cookie with creme filling, made by Nabisco since 1912."},
    {"answer": "AREA",  "category": "general",      "definition": "The extent of a two-dimensional surface; a region or zone."},
    {"answer": "ALOE",  "category": "nature",       "definition": "A succulent plant whose leaf gel is used to soothe burns and skin irritation."},
    {"answer": "ARIA",  "category": "opera",        "definition": "A long solo vocal piece in an opera or oratorio."},
    {"answer": "EPEE",  "category": "sport",        "definition": "A sharp-pointed dueling sword used in modern fencing."},
    {"answer": "ETUI",  "category": "crosswordese", "definition": "A small ornamental case, typically for sewing needles or other small objects.", "note": "From French. The quintessential crosswordese word."},
    {"answer": "OLEO",  "category": "crosswordese", "definition": "Margarine; a butter substitute made from vegetable oils.", "note": "Short for oleomargarine."},
    {"answer": "EDAM",  "category": "food",         "definition": "A mild Dutch cheese in a round shape, traditionally coated in red wax. Named for the town of Edam."},
    {"answer": "ESAU",  "category": "bible",        "definition": "In Genesis, the elder twin son of Isaac and Rebekah; sold his birthright to his brother Jacob for stew.", "note": "Forefather of the Edomites."},
    {"answer": "ESAI",  "category": "names",        "definition": "Esai Morales, American actor (NYPD Blue, La Bamba, Ozark, Mission: Impossible)."},
    {"answer": "ALEE",  "category": "nautical",     "definition": "On or toward the side of a ship sheltered from the wind; opposite of windward."},
    {"answer": "ANTE",  "category": "general",      "definition": "A required bet placed before a hand of poker; more generally, a stake or price of admission."},
    {"answer": "OBOE",  "category": "music",        "definition": "A double-reed woodwind instrument with a distinctive penetrating tone; orchestras tune to its A."},
    {"answer": "IDEA",  "category": "general",      "definition": "A thought, notion, or mental conception."},
    {"answer": "EDEN",  "category": "bible",        "definition": "The garden of paradise in the Book of Genesis; the original home of Adam and Eve."},
    {"answer": "EWER",  "category": "crosswordese", "definition": "A large wide-mouthed pitcher or jug, often ornamental, for carrying water."},
    {"answer": "OAST",  "category": "crosswordese", "definition": "A kiln for drying hops, malt, or tobacco, especially in southeast England."},
    {"answer": "ANOA",  "category": "crosswordese", "definition": "Either of two species of small wild buffalo native to the Indonesian island of Sulawesi (Celebes)."},
    {"answer": "APSE",  "category": "architecture", "definition": "A semicircular or polygonal recess, usually vaulted, at the end of a church or cathedral."},
    {"answer": "NENE",  "category": "nature",       "definition": "The Hawaiian goose (Branta sandvicensis), state bird of Hawaii."},
    {"answer": "ALOU",  "category": "names",        "definition": "Dominican baseball family: brothers Felipe, Matty, and Jesús Alou played MLB; Felipe's son Moisés Alou also a major-leaguer."},
    {"answer": "ASEA",  "category": "nautical",     "definition": "At sea; on the ocean. Figuratively, bewildered or at a loss."},
    {"answer": "ASHE",  "category": "names",        "definition": "Arthur Ashe (1943–1993), American tennis champion; first Black man to win Wimbledon and the US Open."},
    {"answer": "ELLA",  "category": "names",        "definition": "Ella Fitzgerald (1917–1996), American jazz singer known as the First Lady of Song and Queen of Scat."},
    {"answer": "EERO",  "category": "names",        "definition": "Eero Saarinen (1910–1961), Finnish-American architect of the Gateway Arch and the TWA Flight Center."},
    {"answer": "OTTO",  "category": "names",        "definition": "Common Germanic male given name; the palindrome OTTO appears via figures like Otto von Bismarck, Otto Preminger, and The Simpsons' bus driver."},
    {"answer": "ETNA",  "category": "geography",    "definition": "Mount Etna, the active stratovolcano on Sicily's east coast; the highest volcano in continental Europe."},
    {"answer": "OREL",  "category": "geography",    "definition": "City in western Russia south of Moscow; also Orel Hershiser, Cy Young–winning Dodgers pitcher."},
    {"answer": "EROS",  "category": "mythology",    "definition": "The Greek god of love and desire; son of Aphrodite, equivalent to Roman Cupid."},
    {"answer": "IAGO",  "category": "literature",   "definition": "The treacherous antagonist of Shakespeare's Othello; also the parrot in Disney's Aladdin."},
    {"answer": "OUZO",  "category": "food",         "definition": "A clear Greek anise-flavored aperitif that turns milky white when water is added."},
    {"answer": "STET",  "category": "general",      "definition": "A proofreader's instruction meaning 'let it stand' — disregard the marked correction."},
    {"answer": "EMIR",  "category": "foreign",      "definition": "An Arab prince, chieftain, or ruler; the head of state of an emirate.", "note": "Variant spelling: EMEER."},
    {"answer": "ADIT",  "category": "crosswordese", "definition": "A nearly horizontal passage from the surface into a mine."},
    {"answer": "ESNE",  "category": "crosswordese", "definition": "A laborer or domestic slave in Anglo-Saxon England."},
    {"answer": "ARIL",  "category": "nature",       "definition": "A fleshy outer covering on certain seeds, e.g., the red coat around a pomegranate seed."},
    {"answer": "IOTA",  "category": "general",      "definition": "The ninth letter of the Greek alphabet (Ι, ι); figuratively, an extremely small amount."},

    # ---------- 5-letter staples ----------
    {"answer": "AERIE", "category": "nature",       "definition": "The high nest of a bird of prey such as an eagle or hawk."},
    {"answer": "AIOLI", "category": "food",         "definition": "A garlic mayonnaise originating in Provence and the Mediterranean."},
    {"answer": "ARETE", "category": "geography",    "definition": "A sharp mountain ridge formed by glacial erosion between two cirques."},
    {"answer": "EERIE", "category": "general",      "definition": "Strange and frightening; uncanny."},
    {"answer": "NACRE", "category": "nature",       "definition": "Mother-of-pearl; the iridescent inner shell layer of some mollusks."},
    {"answer": "OATER", "category": "crosswordese", "definition": "Informal term for a Western film."},
    {"answer": "OREAD", "category": "mythology",    "definition": "In Greek mythology, a nymph of mountains and grottoes."},
    {"answer": "SEDER", "category": "religion",     "definition": "The ritual Jewish dinner on the first night (and sometimes second) of Passover."},
    {"answer": "SEINE", "category": "geography",    "definition": "The river that flows through Paris and into the English Channel at Le Havre; also a large vertical fishing net."},
    {"answer": "TAROT", "category": "general",      "definition": "A 78-card deck used for fortune-telling, with 22 Major Arcana and 56 Minor Arcana."},
    {"answer": "THANE", "category": "literature",   "definition": "A Scottish feudal lord ranking below an earl; famously Macbeth, Thane of Cawdor."},
    {"answer": "TORTE", "category": "food",         "definition": "A rich many-layered cake, especially in Central European tradition (e.g., Sacher torte)."},
    {"answer": "YENTA", "category": "foreign",      "definition": "Yiddish for a gossipy woman or busybody; also the matchmaker character in Fiddler on the Roof."},
    {"answer": "YODEL", "category": "music",        "definition": "To sing with rapid alternation between normal voice and falsetto, in the Alpine tradition."},

    # ---------- Other high-value short fill ----------
    {"answer": "HORA",  "category": "general",      "definition": "An Israeli and Romanian circle dance, traditional at Jewish weddings and celebrations."},
    {"answer": "ARES",  "category": "mythology",    "definition": "The Greek god of war; equivalent to Roman Mars."},
    {"answer": "HERA",  "category": "mythology",    "definition": "Queen of the Greek gods; wife and sister of Zeus; goddess of marriage."},
    {"answer": "ODIN",  "category": "mythology",    "definition": "The chief god of Norse mythology; father of Thor; ruler of Asgard."},
    {"answer": "AIDA",  "category": "opera",        "definition": "An 1871 opera by Giuseppe Verdi about an Ethiopian princess enslaved in Egypt."},
    {"answer": "NILE",  "category": "geography",    "definition": "Major north-flowing African river, traditionally the longest river in the world."},
    {"answer": "ARNO",  "category": "geography",    "definition": "The principal river of Tuscany, flowing through Florence and Pisa; also Peter Arno, New Yorker cartoonist."},
    {"answer": "URAL",  "category": "geography",    "definition": "Mountain range running north–south through western Russia, conventionally dividing Europe from Asia; also a river of the same name."},
    {"answer": "OMAN",  "category": "geography",    "definition": "Sultanate on the southeast coast of the Arabian Peninsula; capital Muscat."},
    {"answer": "ENYA",  "category": "names",        "definition": "Irish singer (b. 1961) known for ethereal multilayered vocals; hits include 'Orinoco Flow' and 'Only Time'."},
    {"answer": "AVA",   "category": "names",        "definition": "Female given name; notable bearers Ava Gardner (actress) and Ava DuVernay (filmmaker)."},
    {"answer": "ORR",   "category": "names",        "definition": "Bobby Orr, Hall of Fame Boston Bruins defenseman who won eight consecutive Norris Trophies (1968–1975)."},
    {"answer": "ELO",   "category": "music",        "definition": "Electric Light Orchestra, English rock band led by Jeff Lynne; hits include 'Mr. Blue Sky' and 'Evil Woman'."},

    # ---------- v1.1 high-frequency gaps (added 2026-05-24) ----------
    # 3-letter interjections — extremely common short fill.
    {"answer": "OOH", "category": "general",   "definition": "Exclamation of surprise, admiration, or pleasure (often paired with 'aah')."},
    {"answer": "AAH", "category": "general",   "definition": "Exclamation of relief, awe, or comfort."},
    {"answer": "OHO", "category": "general",   "definition": "Exclamation indicating surprise or triumph at a discovery."},
    {"answer": "EEK", "category": "general",   "definition": "Exclamation of fright or alarm, traditionally on seeing a mouse."},
    {"answer": "TSE", "category": "names",     "definition": "Syllable in the Wade-Giles romanization of Mao Tse-tung's name; also 'Lao-tse'."},
    {"answer": "TAE", "category": "foreign",   "definition": "Korean for 'kick' (as in tae kwon do); also Scottish dialect for 'to'."},

    # 3-letter compass directions (we already have ESE).
    {"answer": "ENE", "category": "abbr",      "definition": "East-northeast — the compass point between east and northeast."},
    {"answer": "NNE", "category": "abbr",      "definition": "North-northeast — the compass point between north and northeast."},
    {"answer": "NNW", "category": "abbr",      "definition": "North-northwest — the compass point between north and northwest."},
    {"answer": "SSE", "category": "abbr",      "definition": "South-southeast — the compass point between south and southeast."},
    {"answer": "SSW", "category": "abbr",      "definition": "South-southwest — the compass point between south and southwest."},
    {"answer": "WNW", "category": "abbr",      "definition": "West-northwest — the compass point between west and northwest."},
    {"answer": "WSW", "category": "abbr",      "definition": "West-southwest — the compass point between west and southwest."},

    # 4-letter very-high-frequency common fill.
    {"answer": "ODOR", "category": "general",  "definition": "A distinctive smell, often unpleasant."},
    {"answer": "ELSE", "category": "general",  "definition": "Otherwise; in addition; different from what has been mentioned."},
    {"answer": "ORAL", "category": "general",  "definition": "Spoken rather than written; or relating to the mouth."},
    {"answer": "ANEW", "category": "general",  "definition": "In a new or different way; once more, afresh."},
    {"answer": "EELS", "category": "nature",   "definition": "Plural of eel (any of various elongated, snake-like fish)."},

    # 4-letter geography — Middle East giants.
    {"answer": "IRAN", "category": "geography","definition": "Country in western Asia, formerly Persia; capital Tehran."},
    {"answer": "IRAQ", "category": "geography","definition": "Country in western Asia, between Iran and Saudi Arabia; capital Baghdad."},

    # 4-letter rivers / niche-but-frequent.
    {"answer": "YSER", "category": "geography","definition": "River in northern France and Belgium; site of major World War I battles."},
    {"answer": "AARE", "category": "geography","definition": "The longest river entirely within Switzerland (also spelled Aar)."},
    {"answer": "ARAL", "category": "geography","definition": "Aral Sea — a formerly large endorheic lake in Central Asia, now largely dried up."},
    {"answer": "EBRO", "category": "geography","definition": "Major river of northeastern Spain, flowing east to the Mediterranean."},
    {"answer": "ELHI", "category": "general",  "definition": "Adjective covering grades K–12 (elementary plus high school)."},
    {"answer": "UTNE", "category": "names",    "definition": "Utne Reader, an American alternative-press magazine founded by Eric Utne."},

    # 5-letter extremely high-frequency common fill.
    {"answer": "ARENA", "category": "general", "definition": "A flat central area surrounded by tiered seating for sports or performances."},
    {"answer": "NAIVE", "category": "general", "definition": "Showing a lack of experience, wisdom, or judgment."},
    {"answer": "OCEAN", "category": "geography","definition": "A very large expanse of sea, especially one of the Earth's five named oceans."},
    {"answer": "INANE", "category": "general", "definition": "Silly; lacking sense or substance."},
    {"answer": "OZONE", "category": "science", "definition": "A pale-blue gas (O₃) forming a layer in the stratosphere; colloquially, fresh air."},

    # 5-letter recurring proper nouns.
    {"answer": "ETHEL", "category": "names",   "definition": "Female given name; notable bearers include Ethel Merman (singer/actress) and Ethel Kennedy."},
    {"answer": "RENEE", "category": "names",   "definition": "French-origin female given name; notable bearers Renée Zellweger (actress) and Renée Fleming (soprano)."},
    {"answer": "LASSO", "category": "general", "definition": "A rope with a running noose for catching cattle; also the title character of the TV series Ted Lasso."},
    {"answer": "MAMET", "category": "literature","definition": "David Mamet, Pulitzer-winning American playwright (Glengarry Glen Ross, Speed-the-Plow)."},
    {"answer": "ORONO", "category": "geography","definition": "Town in Maine, home of the main campus of the University of Maine."},
    {"answer": "OUTRE", "category": "foreign", "definition": "Unconventional, bizarre, or extreme (from French outré, 'beyond')."},

    # ---------- v1.2 expansion (added 2026-05-25) ----------
    # Greek letters — extremely common 3-letter crosswordese fill (we
    # already have ETA and IOTA; this rounds out the alphabet's most-clued).
    {"answer": "RHO", "category": "general", "definition": "Seventeenth letter of the Greek alphabet (Ρ, ρ); equivalent to Latin R."},
    {"answer": "PHI", "category": "general", "definition": "Twenty-first letter of the Greek alphabet (Φ, φ); used in math and physics."},
    {"answer": "PSI", "category": "general", "definition": "Twenty-third letter of the Greek alphabet (Ψ, ψ); symbol used in physics and psychology."},
    {"answer": "CHI", "category": "general", "definition": "Twenty-second letter of the Greek alphabet (Χ, χ); equivalent to KH."},
    {"answer": "TAU", "category": "general", "definition": "Nineteenth letter of the Greek alphabet (Τ, τ); equivalent to Latin T."},
    # MU and NU dropped 2026-05-26 — XD corpus shows them at 0 and 3
    # appearances respectively. Greek-letter answers only appear when the
    # constructor needs the specific letter pattern, and MU/NU are too short
    # to fit useful patterns.

    # Rivers — high-frequency geography clue answers.
    {"answer": "NEVA",  "category": "geography", "definition": "River flowing through St. Petersburg, Russia, into the Gulf of Finland."},
    {"answer": "ELBE",  "category": "geography", "definition": "Major river of central Europe, flowing through the Czech Republic and Germany to the North Sea."},
    {"answer": "ODER",  "category": "geography", "definition": "River along the Germany–Poland border, flowing to the Baltic Sea."},
    {"answer": "TIBER", "category": "geography", "definition": "Third-longest river in Italy, flowing through Rome."},

    # Mythology — common deity / figure names that recur in clues.
    {"answer": "ZEUS", "category": "mythology", "definition": "King of the Greek gods; ruler of Mount Olympus and god of sky and thunder."},
    {"answer": "THOR", "category": "mythology", "definition": "Norse god of thunder; wielder of the hammer Mjölnir; son of Odin."},
    {"answer": "NIKE", "category": "mythology", "definition": "Greek goddess of victory; also the sneaker brand named for her."},
    {"answer": "ECHO", "category": "mythology", "definition": "Mountain nymph in Greek myth who, cursed, could only repeat the last words spoken to her; pined away for Narcissus."},
    {"answer": "ISIS", "category": "mythology", "definition": "Ancient Egyptian goddess of magic, motherhood, and protection; wife of Osiris."},
    {"answer": "IRIS", "category": "mythology", "definition": "Greek goddess of the rainbow and messenger of the gods; also a flower genus and the eye's colored ring."},

    # Bible — short, recurring biblical names.
    {"answer": "ABEL", "category": "bible", "definition": "Second son of Adam and Eve, killed by his brother Cain."},
    {"answer": "EVE",  "category": "bible", "definition": "In Genesis, the first woman; partner of Adam."},
    {"answer": "ASA",  "category": "bible", "definition": "Third king of Judah; known for religious reforms. Also a common short name (Asa Hutchinson, Asa Butterfield)."},
    {"answer": "ARK",  "category": "bible", "definition": "Noah's vessel that survived the Flood; also the Ark of the Covenant."},

    # Names — recurring proper nouns in modern crosswords.
    {"answer": "UMA",  "category": "names", "definition": "Uma Thurman, American actress (Pulp Fiction, Kill Bill)."},
    {"answer": "ARLO", "category": "names", "definition": "Arlo Guthrie, American folk singer best known for 'Alice's Restaurant'."},
    {"answer": "IDA",  "category": "names", "definition": "Common female given name; notable bearers include actress Ida Lupino and journalist Ida B. Wells."},
    {"answer": "OONA", "category": "names", "definition": "Female given name; notably Oona O'Neill Chaplin (Eugene O'Neill's daughter, Charlie Chaplin's wife) and actress Oona Chaplin (her granddaughter)."},
    {"answer": "SADE", "category": "names", "definition": "British band fronted by Sade Adu; hits include 'Smooth Operator' and 'No Ordinary Love'."},
    {"answer": "ABBA", "category": "names", "definition": "Swedish pop group of the 1970s; hits include 'Dancing Queen' and 'Mamma Mia'."},

    # Other common short crosswordese fill.
    {"answer": "OREOS", "category": "brand",   "definition": "Plural of OREO (chocolate sandwich cookie)."},
    {"answer": "OASES", "category": "general", "definition": "Plural of oasis — fertile spots in a desert fed by underground water."},
    {"answer": "OCTET", "category": "music",   "definition": "A group of eight, especially of musicians or a piece for eight voices/instruments."},

    # ---------- v1.3 expansion (added 2026-05-26, top-frequency from XD corpus) ----------
    # These were the highest-frequency 3–5-letter answers missing from the deck
    # per the XD corpus (~8M clue rows from NYT/LAT/WSJ/USA Today/Newsday +
    # indies). Counts shown in parentheses are total XD appearances.
    {"answer": "ERIE", "category": "geography",   "definition": "Lake Erie, the fourth-largest Great Lake; also the Pennsylvania city on its shore. (XD: 5,989)"},
    {"answer": "ALA",  "category": "foreign",     "definition": "Latin / Italian 'in the style of' (e.g., 'à la mode'); also the abbreviation for the U.S. state of Alabama. (XD: 4,559)"},
    {"answer": "SPA",  "category": "general",     "definition": "A commercial establishment offering bathing, massage, and other health treatments. (XD: 4,479)"},
    {"answer": "ODE",  "category": "literature",  "definition": "A lyric poem in elaborate, formal stanzas, typically addressed to a subject (e.g., Keats's 'Ode on a Grecian Urn'). (XD: 4,233)"},
    {"answer": "IRA",  "category": "names",       "definition": "Individual Retirement Account; also a male given name (Ira Gershwin, Ira Glass). (XD: 4,204)"},
    {"answer": "OLE",  "category": "foreign",     "definition": "Spanish exclamation of approval, especially at bullfights or flamenco performances. (XD: 4,192)"},
    {"answer": "ASIA", "category": "geography",   "definition": "The largest continent by area and population. (XD: 3,864)"},
    {"answer": "ESS",  "category": "general",     "definition": "The letter S; also a winding road shape. (XD: 3,811)"},
    {"answer": "ALAS", "category": "general",     "definition": "Exclamation of grief, sorrow, or pity. (XD: 3,555)"},
    {"answer": "NEE",  "category": "foreign",     "definition": "French for 'born' (née) — used in obituaries and wedding notices to introduce a maiden name. (XD: 3,423)"},
    {"answer": "ISLE", "category": "geography",   "definition": "A small island; often a place name (Isle of Man, Isle of Wight). (XD: 3,371)"},
    {"answer": "ETAL", "category": "general",     "definition": "Abbreviation of Latin 'et alii' — 'and others'. Used in citations and lists. (XD: 3,222)"},
    {"answer": "OSLO", "category": "geography",   "definition": "Capital and largest city of Norway. (XD: 3,115)"},
    {"answer": "TSAR", "category": "general",     "definition": "Emperor of Russia before 1917 (also spelled CZAR). (XD: 3,043)"},
    {"answer": "ALTO", "category": "music",       "definition": "A vocal or instrumental range between soprano and tenor; also the lowest female singing voice."},
    {"answer": "AHA",  "category": "general",     "definition": "Exclamation of surprise, recognition, or triumph. (XD: 2,987)"},
    {"answer": "IDLE", "category": "names",       "definition": "Eric Idle, English comedian of Monty Python's Flying Circus; also a verb meaning to run without doing useful work. (XD: 2,831)"},
    {"answer": "ANON", "category": "general",     "definition": "Anonymous; also archaic for 'soon' or 'in a moment'. (XD: 2,819)"},
    {"answer": "OGRE", "category": "general",     "definition": "A monstrous giant in folklore who eats humans; figuratively, a cruel person. (XD: 2,801)"},
    {"answer": "ENOS", "category": "bible",       "definition": "Son of Seth and grandson of Adam in Genesis. (XD: 2,712)"},
    {"answer": "ELAN", "category": "foreign",     "definition": "Vigor, style, and enthusiasm in action (from French élan). (XD: 2,703)"},
    {"answer": "ALEC", "category": "names",       "definition": "Male given name; notable bearers Alec Baldwin, Alec Guinness, Smart Alec. (XD: 2,663)"},
    {"answer": "OPAL", "category": "general",     "definition": "An iridescent silica gemstone; the October birthstone. (XD: 2,660)"},
    {"answer": "ETON", "category": "names",       "definition": "Eton College, an English boarding school for boys founded in 1440; long associated with British prime ministers and royals. (XD: 2,652)"},
]
