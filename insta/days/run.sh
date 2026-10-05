set -e
cd /workspace/insta
python3 make_insta.py days/2026-10-01.json --ids fd111a107a,389ecb8687,06d1800627,12c6ea1b55,04e3c6023b,d4cb600701,9b59a27765 --past --out /workspace/insta/2026-10-01
python3 make_insta.py days/2026-10-02.json --ids cf70e45eba,575ad95eff,c702eea40d,96745ca669,94d6feedab,e46e80d39d,10d8148893 --past --out /workspace/insta/2026-10-02
python3 make_insta.py days/2026-10-03.json --ids 13194ceddd,3cdb3f7082,4df91bd21d,bf140614a0,0b0baf0793,ae8f87040d,83367cdd4c --past --out /workspace/insta/2026-10-03
