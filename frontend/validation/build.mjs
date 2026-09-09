/** Builds the actual components into one local IIFE for an about:blank harness. */
import { build } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'
const outDir = process.argv[2]
if (!outDir || !path.isAbsolute(outDir)) throw new Error('Pass an absolute validation-only output directory')
await build({ configFile:false, plugins:[vue()], root:process.cwd(),
  build:{outDir,emptyOutDir:true,cssCodeSplit:false,rollupOptions:{input:'validation/entry.ts',output:{format:'iife',name:'WorkspaceValidation',inlineDynamicImports:true,entryFileNames:'validation.js',assetFileNames:'[name][extname]'}}} })
