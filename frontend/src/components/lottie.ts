import { DotLottieReact, setWasmUrl } from '@lottiefiles/dotlottie-react'
import wasmUrl from '@lottiefiles/dotlottie-web/dotlottie-player.wasm?url'

// The player fetches its WASM from a public CDN unless told otherwise. Serve the copy bundled
// with the portal, so the animations work offline and the page asks nothing of a third party.
setWasmUrl(wasmUrl)

export { DotLottieReact }
