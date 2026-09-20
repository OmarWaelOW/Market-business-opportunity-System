# KMeans uses base R stats so no additional R package is required.
args <- commandArgs(trailingOnly = TRUE)
input <- read.csv(args[[1]], stringsAsFactors = FALSE)
output_path <- args[[2]]
cluster_count <- as.integer(args[[3]])
features <- input[, c("demand_growth", "supplier_coverage", "opportunity_gap")]
set.seed(42)
model <- stats::kmeans(scale(features), centers = cluster_count, nstart = 25)
input$cluster_id <- model$cluster
centers <- aggregate(input[, c("demand_growth", "supplier_coverage", "opportunity_gap")], list(cluster_id = model$cluster), mean)
centers$label <- ifelse(centers$opportunity_gap == max(centers$opportunity_gap), "High demand, low coverage",
                        ifelse(centers$demand_growth >= centers$supplier_coverage, "Demand-led opportunity", "Well-covered market"))
input$cluster <- centers$label[match(input$cluster_id, centers$cluster_id)]
input$cluster_id <- NULL
write.csv(input, output_path, row.names = FALSE)