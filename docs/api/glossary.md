---
icon: lucide/book-marked
tags:
  - api
---

# Glossary

Indexes model instances by the product IRIs they declare. Nothing produced returns `None` and the caller records a cutoff leaf; two producers raise [`AmbiguousProducer`](errors.md), because that is a data error rather than something to settle by silent precedence.

::: trailrunner.orchestration.glossary
