# Export the open science blog archive (https://github.com/Lakens/open_science_blogs, blog_data.rds) to JSON for
# blog_candidates.py: one record per post with id, author, date, title, url, plain text, and the links in the post
# (address and link text, taken from the HTML).
# Usage: Rscript export_blogs.R <blog_data.rds> <blogs.json>
suppressMessages(library(jsonlite))
args <- commandArgs(TRUE)
d <- readRDS(args[1])
get_links <- function(h) {
  m <- regmatches(h, gregexpr('<a[^>]+href="[^"]+"[^>]*>.*?</a>', h, perl = TRUE))[[1]]
  if (!length(m)) return(list())
  href <- sub('^.*?href="([^"]+)".*$', "\\1", m, perl = TRUE)
  txt <- trimws(gsub("<[^>]+>", "", sub("^<a[^>]*>", "", sub("</a>$", "", m))))
  lapply(seq_along(m), function(i) list(u = href[i], t = substr(txt[i], 1, 200)))
}
out <- lapply(seq_len(nrow(d)), function(i) list(id = d$id[i], a = d$author[i], d = as.character(as.Date(d$date_clean[i])),
  t = d$title[i], url = d$url[i], x = d$content[i], l = get_links(d$content_html[i])))
writeLines(toJSON(out, auto_unbox = TRUE), args[2], useBytes = TRUE)
cat("written", length(out), "posts\n")
