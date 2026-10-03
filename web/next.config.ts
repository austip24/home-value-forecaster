import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // The dashboard reads its data from web/data/ (written by `forecaster
  // export-web`) at request time. Ship that bundle with the page's server
  // function (the only route that reads it), since the readers' dynamic paths
  // aren't traced automatically.
  outputFileTracingIncludes: {
    "/": ["./data/**/*"],
  },
}

export default nextConfig
