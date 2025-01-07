#!/bin/bash

mkdir -p bitfocus-modules-data

(
    cd bitfocus-modules-data
    if [[ ! -d companion-bundled-modules ]]; then
        git clone --depth=1 https://github.com/ossia/companion-bundled-modules
        rm -rf companion-bundled-modules/.git
    fi
)

for NODE_ARCH in linux-arm64.tar.xz linux-x64.tar.xz darwin-x64.tar.gz darwin-arm64.tar.gz win-x64.zip; do
    (
        cd bitfocus-modules-data
        for NODE_VERSION in 18.20.5 22.12.0; do
            mkdir -p node-runtime/$NODE_VERSION
            curl -L https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-$NODE_ARCH -o $NODE_VERSION-$NODE_ARCH
            unar -q $NODE_VERSION-$NODE_ARCH -o node-runtime/
            rm $NODE_VERSION-$NODE_ARCH
        done
        
        (
            cd node-runtime
            find . -name npm -exec rm -rf {} \;
        )
        cd ..
        ARCH_NOEXT=$(echo $NODE_ARCH | cut -d'.' -f1)
        cp addon.json bitfocus-modules-data/
        7z a bitfocus-modules-data-$ARCH_NOEXT.zip bitfocus-modules-data
    )
done

#
# win-x64.zip

#https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-arm64.tar.xz
#https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-x64.tar.xz

#https://nodejs.org/dist/v22.12.0/node-v22.12.0-darwin-x64.tar.gz
#https://nodejs.org/dist/v22.12.0/node-v22.12.0-darwin-arm64.tar.gz

#https://nodejs.org/dist/v22.12.0/node-v22.12.0-win-x64.zip
#https://nodejs.org/dist/v18.20.5/node-v18.20.5-win-x64.zip

