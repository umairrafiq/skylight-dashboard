#!/bin/bash

HA_URL="https://10.0.0.183:8123"
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI5MDcxNmM5ZTAwODU0NTJkYjc3MWYzMTFmZWM5ZTAzNiIsImlhdCI6MTc2OTY1OTM3MywiZXhwIjoyMDg1MDE5MzczfQ.BeLwAlwTaJVi-E3TR4RZSi7hjIF5XIMjpw_Bd93EZ0U"

add_birthday() {
    local month=$1
    local day=$2
    local name=$3
    local year=$4
    
    local start_date="2026-$(printf "%02d" $month)-$(printf "%02d" $day)"
    local end_date=$(date -d "$start_date + 1 day" +%Y-%m-%d)
    
    local summary="🎂 $name's Birthday"
    local desc=""
    if [ -n "$year" ]; then
        desc="Born in $year"
    fi
    
    echo "Adding: $summary on $start_date"
    
    curl -s -k -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"entity_id\": \"calendar.family\",
            \"summary\": \"$summary\",
            \"description\": \"$desc\",
            \"start_date\": \"$start_date\",
            \"end_date\": \"$end_date\",
            \"rrule\": \"FREQ=YEARLY\"
        }" \
        "$HA_URL/api/services/calendar/create_event" > /dev/null
    
    sleep 0.3
}

add_anniversary() {
    local month=$1
    local day=$2
    local name=$3
    local year=$4
    
    local start_date="2026-$(printf "%02d" $month)-$(printf "%02d" $day)"
    local end_date=$(date -d "$start_date + 1 day" +%Y-%m-%d)
    
    local summary="💍 $name Anniversary"
    local desc=""
    if [ -n "$year" ]; then
        desc="Since $year"
    fi
    
    echo "Adding: $summary on $start_date"
    
    curl -s -k -X POST \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"entity_id\": \"calendar.family\",
            \"summary\": \"$summary\",
            \"description\": \"$desc\",
            \"start_date\": \"$start_date\",
            \"end_date\": \"$end_date\",
            \"rrule\": \"FREQ=YEARLY\"
        }" \
        "$HA_URL/api/services/calendar/create_event" > /dev/null
    
    sleep 0.3
}

echo "=== Adding Birthdays & Anniversaries to Family Calendar ==="
echo ""

# January
add_birthday 1 21 "Minhaal" "2024"

# February
add_birthday 2 25 "Babu Ji"

# March
add_birthday 3 3 "Hamad"
add_anniversary 3 9 "Humza & Alisha Wedding"
add_birthday 3 9 "Alisha"

# April
add_birthday 4 3 "Aaban"
add_birthday 4 11 "Banno"
add_birthday 4 17 "Humza"
add_birthday 4 28 "Ryyan"

# May
add_birthday 5 2 "Solat"
add_anniversary 5 2 "Aapa"
add_birthday 5 13 "Sadaf"
add_anniversary 5 20 "Guli"

# June
add_birthday 6 6 "Ahmad"
add_birthday 6 20 "Umair"
add_birthday 6 20 "Sofiya"
add_birthday 6 20 "Aalya"

# July
add_birthday 7 9 "Hamadan"
add_birthday 7 12 "Rina"
add_birthday 7 16 "Mikhail" "2021"
add_birthday 7 19 "Safia"

# August
add_birthday 8 16 "Sanum"
add_birthday 8 16 "Hadi"
add_birthday 8 24 "Sherry"

# September
add_birthday 9 2 "Shami"
add_birthday 9 3 "Amaaira" "2020"
add_birthday 9 8 "Saba"

# October
add_birthday 10 1 "Ehsan" "1951"
add_birthday 10 2 "Aaleen"
add_birthday 10 3 "Marium"

# November
add_anniversary 11 6 "Sadaf & Sanum Wedding"
add_birthday 11 7 "Maheen"
add_birthday 11 30 "Guli Khanum"

# December
add_birthday 12 5 "Eemanay" "2015"
add_birthday 12 12 "Anaya" "2012"

echo ""
echo "=== Done! Added all events to Family Calendar ==="
