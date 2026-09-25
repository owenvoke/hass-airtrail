# HASS AirTrail

[![Latest Version][ico-version]][link-releases]
[![Software License][ico-license]](LICENSE.md)
[![Build Status][ico-github-actions]][link-github-actions]
[![Buy us a tree][ico-treeware-gifting]][link-treeware-gifting]

An [AirTrail](https://github.com/johanohly/AirTrail) integration for Home Assistant

## Install

### Via HACS

1. Install the [Home Assistant Community Store (HACS)](https://hacs.xyz/docs/setup/download)
2. Add AirTrail as a custom repository. See [the HACS FAQs](https://hacs.xyz/docs/faq/custom_repositories) and
   add `https://github.com/owenvoke/hass-airtrail`
3. Select `integration` as the category
4. You should now be able to install AirTrail via HACS
5. Once installation is complete, restart Home Assistant
6. In the HA UI, go to `Configuration -> Integrations`, click `+` and search for `AirTrail`

### Manual

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`)
2. If you do not have a `custom_components` directory there, you need to create it
3. Add the `airtrail` directory and its contents from this repository to the `custom_components` directory in your Home
   Assistant configuration directory
4. Restart Home Assistant
5. In the HA UI, go to `Configuration -> Integrations`, click `+` and search for `AirTrail`

## Usage

This can be configured fully via the Integrations interface. Click the following link to add a new AirTrail instance.

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=airtrail)

You will need the URL of your AirTrail instance and an API key, which can be created in AirTrail under
`Settings -> Security`. The key only needs permission to read your own flights.

### Options

| Option                  | Default | Description                                            |
|-------------------------|---------|--------------------------------------------------------|
| Upcoming flights window | 30 days | How far ahead the "Upcoming flights" sensor looks      |
| Past flights window     | 30 days | How far back the "Past flights" sensor looks           |
| Scan interval           | 30 mins | How often AirTrail is polled for changes               |

### Entities

| Entity                     | Type          | Description                                                                 |
|----------------------------|---------------|-----------------------------------------------------------------------------|
| Next flight                | Sensor        | Departure time of the next flight, with full flight details as attributes   |
| Last flight                | Sensor        | Arrival time of the most recent flight, with full flight details            |
| Upcoming flights           | Sensor        | Number of flights in the upcoming window, listed in the `flights` attribute |
| Past flights               | Sensor        | Number of flights in the past window, listed in the `flights` attribute     |
| In flight                  | Binary sensor | On while a flight is between departure and arrival                          |
| Flights                    | Calendar      | Every flight with a known date, as calendar events                          |
| Total flights              | Sensor        | Number of completed flights ¹                                               |
| Total distance             | Sensor        | Total great-circle distance flown ¹                                         |
| Total flight time          | Sensor        | Total time spent in the air ¹                                               |
| Airports visited           | Sensor        | Number of unique airports visited ¹                                         |
| Top airline/airport/aircraft/route | Sensor | Your most frequent airline, airport, aircraft type and route ¹          |

¹ Requires an AirTrail version that provides the `/api/stats` endpoint. These sensors are not created otherwise.

Each flight exposes attributes including the flight number, airline, origin and destination (code, name, city and
country), departure and arrival times (in UTC and in the airports' local time), duration, distance, terminals, gates,
aircraft type and registration, your seat, seat class and reason for travel, other passengers and any notes.

Flights that are only recorded to the month or year are excluded from the time-based sensors and the calendar.

### Card

The integration includes a Mushroom-style dashboard card, which is loaded automatically (no resource needs adding). It
shows your next flight (or live progress while you're in the air), statistic chips and a list of upcoming or past
flights. Within 24 hours of departure the next flight is highlighted with a countdown, terminal and gate, and while
you're in the air it shows the time remaining and local arrival time. Search for "AirTrail" when adding a card to use
the visual editor, or add it in YAML:

```yaml
type: custom:airtrail-card
```

| Option        | Default                                                                  | Description                                          |
|---------------|--------------------------------------------------------------------------|------------------------------------------------------|
| `device`      | The first AirTrail device                                                | The AirTrail device to show                          |
| `title`       | None                                                                     | A title above the card                               |
| `color`       | AirTrail blue                                                            | Accent colour, a theme colour name (e.g. `purple`) or any CSS colour |
| `show_header` | `true`                                                                   | Show the next (or current) flight                    |
| `stats`       | `upcoming_flights`, `total_flights`, `total_distance`, `total_flight_time` | Statistic chips to show, in order ²                  |
| `lists`       | `[upcoming]`                                                             | Flight lists to show, in order: `upcoming` and/or `past` (`[]` hides them) |
| `max_flights` | `5`                                                                      | Maximum number of flights in each list               |
| `entry_details` | `flight_number`, `airline`, `departure_time`, `relative`               | What each list entry shows, in order ³               |
| `route`       | `both`                                                                   | How routes are shown: `codes` (`LHR → JFK`), `locations` (`London → New York`) or `both` |

² Any of `upcoming_flights`, `past_flights`, `total_flights`, `total_distance`, `total_flight_time`,
`airports_visited`, `top_airline`, `top_airport`, `top_aircraft` and `top_route`.

³ Any of `flight_number`, `airline`, `departure_time`, `arrival_time`, `duration`, `distance`, `aircraft`,
`seat`, `seat_class` and `relative` (the time until or since the flight, shown on the right).

Tapping the next flight or any flight in the lists expands it to show all of its details (airports, local times,
terminals and gates, aircraft, seat, duration, distance, other passengers and notes). Tapping a statistic opens the
entity's details. The card uses Mushroom's theme variables, so
it matches Mushroom cards and themes, but Mushroom doesn't need to be installed.

### Example

Send a notification with your gate when a flight is three hours away:

```yaml
automation:
  - alias: "Flight reminder"
    triggers:
      - trigger: calendar
        event: start
        offset: "-3:00:00"
        entity_id: calendar.airtrail_airtrail_example_com_flights
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "{{ trigger.calendar_event.summary }}"
          message: >
            Departing {{ state_attr('sensor.airtrail_airtrail_example_com_next_flight', 'departure_local') }}
            from gate {{ state_attr('sensor.airtrail_airtrail_example_com_next_flight', 'departure_gate') or 'TBC' }}
```

## Change log

Please see [GitHub Releases][link-releases] for more information on what has changed recently.

## Security

If you discover any security related issues, please email security@voke.dev instead of using the issue tracker.

## Credits

- [Owen Voke][link-author]
- [All Contributors][link-contributors]

## License

The MIT License (MIT). Please see [License File](LICENSE.md) for more information.

## Treeware

You're free to use this package, but if it makes it to your production environment please consider buying the world a tree.

It’s now common knowledge that one of the best tools to tackle the climate crisis and keep our temperatures from rising above 1.5C is to plant trees. If you support this package and contribute to the Treeware forest you’ll be creating employment for local families and restoring wildlife habitats.

You can buy trees [here][link-treeware-gifting].

Read more about Treeware at [treeware.earth][link-treeware].

[ico-version]: https://img.shields.io/github/v/release/owenvoke/hass-airtrail.svg?style=flat-square&sort=semver
[ico-license]: https://img.shields.io/badge/license-MIT-brightgreen.svg?style=flat-square
[ico-github-actions]: https://img.shields.io/github/actions/workflow/status/owenvoke/hass-airtrail/tests.yml?branch=main&style=flat-square
[ico-treeware-gifting]: https://img.shields.io/badge/Treeware-%F0%9F%8C%B3-lightgreen?style=flat-square

[link-releases]: https://github.com/owenvoke/hass-airtrail/releases
[link-github-actions]: https://github.com/owenvoke/hass-airtrail/actions
[link-treeware]: https://treeware.earth
[link-treeware-gifting]: https://ecologi.com/owenvoke?gift-trees
[link-author]: https://github.com/owenvoke
[link-contributors]: ../../contributors
