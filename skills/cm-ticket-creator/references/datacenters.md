# Datacenter ID Mappings for CM Tickets

CM tickets use two multi-select datacenter fields with **different option IDs**.

## Datacenters (`customfield_17280`)

| Code | ID |
|------|------|
| AM2 | 14936 |
| DFW3 | 17009 |
| FR4 | 14938 |
| FRA2 | 16892 |
| LON3 | 18185 |
| MAA2 | — |
| MEL2 | 14941 |
| RUH1 | 17008 |
| SIN2 | 17007 |
| SJC1 | 14966 |
| SJC2 | 16627 |
| SV5 | 14943 |
| ZUR2 | 16824 |

## Impacted Datacenters (`customfield_27178`)

| Code | ID |
|------|------|
| AM2 | 38721 |
| Cloud GCP | 38718 |
| DFW3 | 38744 |
| FR4 | 38750 |
| FRA2 | 38752 |
| LON3 | 38773 |
| MAA2 | 38776 |
| MEL2 | 38781 |
| RUH1 | 38813 |
| SIN2 | 38822 |
| SJC1 | 38824 |
| SJC2 | 38825 |
| SV5 | 38829 |
| ZUR2 | 38845 |

## Region Classification

Used for inferring maintenance window times.

| Region | Datacenters |
|--------|-------------|
| US | DFW3, SJC1, SJC2, SV5 |
| EU | AM2, FR4, FRA2, LON3, ZUR2 |
| APAC | MEL2, SIN2, MAA2 |
| MEA | RUH1 |
