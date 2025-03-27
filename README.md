# TSU Data
Scripts to read/transform/save data from Turbo Sliders Unlimited. 

The game can export two different result files in different not-easy-to-extract formats. This repository offers scripts to read/combine them and export them to a simple csv file. 

You can find example files in `input_files` directory. 

## Time Format

In all files you need to divide times by 10000 to get seconds.

## The json file

Content Summary:
- json format (surprise)
- basic event data:
    - time, 
    - event type 
    - track
- within `players` key:
    - name
    - steam id
    - clan tag
    - flag (country)
    - start position 
    - vehicle (name and guid from steam)
    - indirectly: order in this list defines player index starting from 0
- within `raceStats`->`raceRanking`->`entries`:
    - player index
    - race time
    - laps completed
    - last checkpoint (in case multiple players didn't manage to finish until timer ran out)
- within `raceStats`->`lapRanking`->`entries` (fastest lap by driver):
    - player index
    - lap time
    - cFlags (1=>lap with collision, 2=>lap with draft, 3=>lap with both)
    - lap
- within `raceStats`->`checkpoints`->`checkpointToSector`:
    -  `-1` means regular checkpoint
    - `0,1,2,...` sectors
- within `raceStats`->`checkpoints`->`sectorToCheckpoint`:
    - checkpoint indices of sectors
- within `playerStats`:
    - startTime (countdown at race start) which you should substract from all checkpoint times
    - lapsToFinish
    - checkpointTimes:
        - for every lap one entry:
            - cFlag (1=>lap with collision, 2=>lap with draft, 3=>lap with both)
            - all checkpoint times


## The log file

Content Summary
- space limited sections of data dumps
- player section:
    - player index
    - player steam id
    - team id
    - name (clan tag and driver name)
- tire compound section (optional):
    - tire compound index
    - tire compound name
    - tire max wear
    - tire performance
- fuel section (optional):
    - max fuel (fuel amount at 100%)
- event section has one entry per event 
    - possible events:
        - Start (when lights go out)
        - Lap (when driver completes a lap expect if finish)
        - PitIn (car stops in pit lane)
        - PitOut (car continues after pit stop)
        - node: there is no EnteredPitLane/ExitedPitLane event right now, PitIn/PitOut refer to the car stoping/continueing into/out of the pit box
    - values for each event:
        - time
        - event type
        - player index
        - laps completed already (not the lap the driver is currently in!)
        - fuel left (divide by max fuel value to get percentage)
        - tire wear (1 - tire wear/tire max wear of the current compoung = tire percentage/condition)
        - tire compound index
        - hit points (divide by 100 to get health in percentage)