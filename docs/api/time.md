---
icon: lucide/calendar-range
tags:
  - api
---

# Time

`Flow.time` is a string in a declared time standard -- by default the XSD datatypes, so `"2030"` in `xsd:gYear`, `"2030-06-15"` in `xsd:date`, `"2030-06-15T08:00:00Z"` in `xsd:dateTime` -- and this module turns the pair into a half-open UTC interval. Every comparison the library makes goes through that interval, never through the string: a model declared for a year covers any day in it. `in_year` and `when` build the `time`/`time_standard` pair a `Flow` expects; `TimeRange` and `year_range` build a model's validity in time. Times read from a file or table with no standard saying how to read them raise [`MissingTimeStandard`](errors.md).

::: trailrunner.core.time
