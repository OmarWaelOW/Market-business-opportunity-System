# Standalone R implementation keeps the Python app independent of rpy2.
args <- commandArgs(trailingOnly = TRUE)
input <- read.csv(args[[1]], stringsAsFactors = FALSE)
output_path <- args[[2]]
horizon <- as.integer(args[[3]])
arima_order <- as.integer(strsplit(args[[4]], ",", fixed = TRUE)[[1]])
input$date <- as.Date(input$date)
results <- list()

for (kind in unique(input$input)) {
  series <- input[input$input == kind, c("date", "price")]
  series <- aggregate(price ~ date, series, mean)
  series <- series[order(series$date), ]
  if (nrow(series) < 12) next
  fit <- tryCatch(stats::arima(series$price, order = arima_order), error = function(e) NULL)
  if (is.null(fit)) next
  prediction <- predict(fit, n.ahead = horizon)
  future_dates <- seq(max(series$date), by = "month", length.out = horizon + 1)[-1]
  future <- data.frame(date = future_dates, input = kind, actual = NA,
                       forecast = as.numeric(prediction$pred),
                       lower = as.numeric(prediction$pred - 1.96 * prediction$se),
                       upper = as.numeric(prediction$pred + 1.96 * prediction$se))
  history <- data.frame(date = series$date, input = kind, actual = series$price,
                        forecast = NA, lower = NA, upper = NA)
  results[[kind]] <- rbind(history, future)
}

if (length(results) == 0) {
  write.csv(data.frame(), output_path, row.names = FALSE)
} else {
  write.csv(do.call(rbind, results), output_path, row.names = FALSE)
}