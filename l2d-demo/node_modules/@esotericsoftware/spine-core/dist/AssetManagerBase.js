/******************************************************************************
 * Spine Runtimes License Agreement
 * Last updated April 5, 2025. Replaces all prior versions.
 *
 * Copyright (c) 2013-2025, Esoteric Software LLC
 *
 * Integration of the Spine Runtimes into software or otherwise creating
 * derivative works of the Spine Runtimes is permitted under the terms and
 * conditions of Section 2 of the Spine Editor License Agreement:
 * http://esotericsoftware.com/spine-editor-license
 *
 * Otherwise, it is permitted to integrate the Spine Runtimes into software
 * or otherwise create derivative works of the Spine Runtimes (collectively,
 * "Products"), provided that each user of the Products must obtain their own
 * Spine Editor license and redistribution of the Products in any form must
 * include this license and copyright notice.
 *
 * THE SPINE RUNTIMES ARE PROVIDED BY ESOTERIC SOFTWARE LLC "AS IS" AND ANY
 * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL ESOTERIC SOFTWARE LLC BE LIABLE FOR ANY
 * DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES,
 * BUSINESS INTERRUPTION, OR LOSS OF USE, DATA, OR PROFITS) HOWEVER CAUSED AND
 * ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
 * THE SPINE RUNTIMES, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *****************************************************************************/
import { TextureAtlas } from "./TextureAtlas.js";
export class AssetManagerBase {
    pathPrefix = "";
    textureLoader;
    downloader;
    cache;
    errors = {};
    toLoad = 0;
    loaded = 0;
    constructor(textureLoader, pathPrefix = "", downloader = new Downloader(), cache = new AssetCache()) {
        this.textureLoader = textureLoader;
        this.pathPrefix = pathPrefix;
        this.downloader = downloader;
        this.cache = cache;
    }
    start(path) {
        this.toLoad++;
        return this.pathPrefix + path;
    }
    success(callback, path, asset) {
        this.toLoad--;
        this.loaded++;
        this.cache.assets[path] = asset;
        this.cache.assetsRefCount[path] = (this.cache.assetsRefCount[path] || 0) + 1;
        if (callback)
            callback(path, asset);
    }
    error(callback, path, message) {
        this.toLoad--;
        this.loaded++;
        this.errors[path] = message;
        if (callback)
            callback(path, message);
    }
    loadAll() {
        let promise = new Promise((resolve, reject) => {
            let check = () => {
                if (this.isLoadingComplete()) {
                    if (this.hasErrors())
                        reject(this.errors);
                    else
                        resolve(this);
                    return;
                }
                requestAnimationFrame(check);
            };
            requestAnimationFrame(check);
        });
        return promise;
    }
    setRawDataURI(path, data) {
        this.downloader.rawDataUris[this.pathPrefix + path] = data;
    }
    loadBinary(path, success = () => { }, error = () => { }) {
        path = this.start(path);
        if (this.reuseAssets(path, success, error))
            return;
        this.cache.assetsLoaded[path] = new Promise((resolve, reject) => {
            this.downloader.downloadBinary(path, (data) => {
                this.success(success, path, data);
                resolve(data);
            }, (status, responseText) => {
                const errorMsg = `Couldn't load binary ${path}: status ${status}, ${responseText}`;
                this.error(error, path, errorMsg);
                reject(errorMsg);
            });
        });
    }
    loadText(path, success = () => { }, error = () => { }) {
        path = this.start(path);
        this.downloader.downloadText(path, (data) => {
            this.success(success, path, data);
        }, (status, responseText) => {
            this.error(error, path, `Couldn't load text ${path}: status ${status}, ${responseText}`);
        });
    }
    loadJson(path, success = () => { }, error = () => { }) {
        path = this.start(path);
        if (this.reuseAssets(path, success, error))
            return;
        this.cache.assetsLoaded[path] = new Promise((resolve, reject) => {
            this.downloader.downloadJson(path, (data) => {
                this.success(success, path, data);
                resolve(data);
            }, (status, responseText) => {
                const errorMsg = `Couldn't load JSON ${path}: status ${status}, ${responseText}`;
                this.error(error, path, errorMsg);
                reject(errorMsg);
            });
        });
    }
    reuseAssets(path, success = () => { }, error = () => { }) {
        const loadedStatus = this.cache.assetsLoaded[path];
        const alreadyExistsOrLoading = loadedStatus !== undefined;
        if (alreadyExistsOrLoading) {
            this.cache.assetsLoaded[path] = loadedStatus
                .then(data => {
                // necessary when user preloads an image into the cache.
                // texture loader is not avaiable in the cache, so we transform in GLTexture at first use
                data = (data instanceof Image || data instanceof ImageBitmap) ? this.textureLoader(data) : data;
                this.success(success, path, data);
                return data;
            })
                .catch(errorMsg => this.error(error, path, errorMsg));
        }
        return alreadyExistsOrLoading;
    }
    loadTexture(path, success = () => { }, error = () => { }) {
        path = this.start(path);
        if (this.reuseAssets(path, success, error))
            return;
        this.cache.assetsLoaded[path] = new Promise((resolve, reject) => {
            let isBrowser = !!(typeof window !== 'undefined' && typeof navigator !== 'undefined' && window.document);
            let isWebWorker = !isBrowser; // && typeof importScripts !== 'undefined';
            if (isWebWorker) {
                fetch(path, { mode: "cors" }).then((response) => {
                    if (response.ok)
                        return response.blob();
                    const errorMsg = `Couldn't load image: ${path}`;
                    this.error(error, path, `Couldn't load image: ${path}`);
                    reject(errorMsg);
                }).then((blob) => {
                    return blob ? createImageBitmap(blob, { premultiplyAlpha: "none", colorSpaceConversion: "none" }) : null;
                }).then((bitmap) => {
                    if (bitmap) {
                        const texture = this.createTexture(path, bitmap);
                        this.success(success, path, texture);
                        resolve(texture);
                    }
                    ;
                });
            }
            else {
                let image = new Image();
                image.crossOrigin = "anonymous";
                image.onload = () => {
                    const texture = this.createTexture(path, image);
                    this.success(success, path, texture);
                    resolve(texture);
                };
                image.onerror = () => {
                    const errorMsg = `Couldn't load image: ${path}`;
                    this.error(error, path, errorMsg);
                    reject(errorMsg);
                };
                if (this.downloader.rawDataUris[path])
                    path = this.downloader.rawDataUris[path];
                image.src = path;
            }
        });
    }
    loadTextureAtlas(path, success = () => { }, error = () => { }, fileAlias) {
        let index = path.lastIndexOf("/");
        let parent = index >= 0 ? path.substring(0, index + 1) : "";
        path = this.start(path);
        if (this.reuseAssets(path, success, error))
            return;
        this.cache.assetsLoaded[path] = new Promise((resolve, reject) => {
            this.downloader.downloadText(path, (atlasText) => {
                try {
                    const atlas = this.createTextureAtlas(path, atlasText);
                    let toLoad = atlas.pages.length, abort = false;
                    if (toLoad === 0) {
                        this.success(success, path, atlas);
                        resolve(atlas);
                        return;
                    }
                    for (let page of atlas.pages) {
                        this.loadTexture(!fileAlias ? parent + page.name : fileAlias[page.name], (imagePath, texture) => {
                            if (!abort) {
                                page.setTexture(texture);
                                if (--toLoad == 0) {
                                    this.success(success, path, atlas);
                                    resolve(atlas);
                                }
                            }
                        }, (imagePath, message) => {
                            if (!abort) {
                                const errorMsg = `Couldn't load texture ${path} page image: ${imagePath}`;
                                this.error(error, path, errorMsg);
                                reject(errorMsg);
                            }
                            abort = true;
                        });
                    }
                }
                catch (e) {
                    const errorMsg = `Couldn't parse texture atlas ${path}: ${e.message}`;
                    this.error(error, path, errorMsg);
                    reject(errorMsg);
                }
            }, (status, responseText) => {
                const errorMsg = `Couldn't load texture atlas ${path}: status ${status}, ${responseText}`;
                this.error(error, path, errorMsg);
                reject(errorMsg);
            });
        });
    }
    loadTextureAtlasButNoTextures(path, success = () => { }, error = () => { }, fileAlias) {
        path = this.start(path);
        if (this.reuseAssets(path, success, error))
            return;
        this.cache.assetsLoaded[path] = new Promise((resolve, reject) => {
            this.downloader.downloadText(path, (atlasText) => {
                try {
                    const atlas = this.createTextureAtlas(path, atlasText);
                    this.success(success, path, atlas);
                    resolve(atlas);
                }
                catch (e) {
                    const errorMsg = `Couldn't parse texture atlas ${path}: ${e.message}`;
                    this.error(error, path, errorMsg);
                    reject(errorMsg);
                }
            }, (status, responseText) => {
                const errorMsg = `Couldn't load texture atlas ${path}: status ${status}, ${responseText}`;
                this.error(error, path, errorMsg);
                reject(errorMsg);
            });
        });
    }
    // Promisified versions of load function
    async loadBinaryAsync(path) {
        return new Promise((resolve, reject) => {
            this.loadBinary(path, (_, binary) => resolve(binary), (_, message) => reject(message));
        });
    }
    async loadJsonAsync(path) {
        return new Promise((resolve, reject) => {
            this.loadJson(path, (_, object) => resolve(object), (_, message) => reject(message));
        });
    }
    async loadTextureAsync(path) {
        return new Promise((resolve, reject) => {
            this.loadTexture(path, (_, texture) => resolve(texture), (_, message) => reject(message));
        });
    }
    async loadTextureAtlasAsync(path) {
        return new Promise((resolve, reject) => {
            this.loadTextureAtlas(path, (_, atlas) => resolve(atlas), (_, message) => reject(message));
        });
    }
    async loadTextureAtlasButNoTexturesAsync(path) {
        return new Promise((resolve, reject) => {
            this.loadTextureAtlasButNoTextures(path, (_, atlas) => resolve(atlas), (_, message) => reject(message));
        });
    }
    setCache(cache) {
        this.cache = cache;
    }
    get(path) {
        return this.cache.assets[this.pathPrefix + path];
    }
    require(path) {
        path = this.pathPrefix + path;
        let asset = this.cache.assets[path];
        if (asset)
            return asset;
        let error = this.errors[path];
        throw Error("Asset not found: " + path + (error ? "\n" + error : ""));
    }
    remove(path) {
        path = this.pathPrefix + path;
        let asset = this.cache.assets[path];
        if (asset.dispose)
            asset.dispose();
        delete this.cache.assets[path];
        delete this.cache.assetsRefCount[path];
        delete this.cache.assetsLoaded[path];
        return asset;
    }
    removeAll() {
        for (let path in this.cache.assets) {
            let asset = this.cache.assets[path];
            if (asset.dispose)
                asset.dispose();
        }
        this.cache.assets = {};
        this.cache.assetsLoaded = {};
        this.cache.assetsRefCount = {};
    }
    isLoadingComplete() {
        return this.toLoad == 0;
    }
    getToLoad() {
        return this.toLoad;
    }
    getLoaded() {
        return this.loaded;
    }
    dispose() {
        this.removeAll();
    }
    // dispose asset only if it's not used by others
    disposeAsset(path) {
        const asset = this.cache.assets[path];
        if (asset instanceof TextureAtlas) {
            asset.dispose();
            return;
        }
        this.disposeAssetInternal(path);
    }
    hasErrors() {
        return Object.keys(this.errors).length > 0;
    }
    getErrors() {
        return this.errors;
    }
    disposeAssetInternal(path) {
        if (this.cache.assetsRefCount[path] > 0 && --this.cache.assetsRefCount[path] === 0) {
            return this.remove(path);
        }
    }
    createTextureAtlas(path, atlasText) {
        const atlas = new TextureAtlas(atlasText);
        atlas.dispose = () => {
            if (this.cache.assetsRefCount[path] <= 0)
                return;
            this.disposeAssetInternal(path);
            for (const page of atlas.pages) {
                page.texture?.dispose();
            }
        };
        return atlas;
    }
    createTexture(path, image) {
        const texture = this.textureLoader(image);
        const textureDispose = texture.dispose.bind(texture);
        texture.dispose = () => {
            if (this.disposeAssetInternal(path))
                textureDispose();
        };
        return texture;
    }
}
export class AssetCache {
    assets = {};
    assetsRefCount = {};
    assetsLoaded = {};
    static AVAILABLE_CACHES = new Map();
    static getCache(id) {
        const cache = AssetCache.AVAILABLE_CACHES.get(id);
        if (cache)
            return cache;
        const newCache = new AssetCache();
        AssetCache.AVAILABLE_CACHES.set(id, newCache);
        return newCache;
    }
    async addAsset(path, asset) {
        this.assetsLoaded[path] = Promise.resolve(asset);
        this.assets[path] = await asset;
    }
}
export class Downloader {
    callbacks = {};
    rawDataUris = {};
    dataUriToString(dataUri) {
        if (!dataUri.startsWith("data:")) {
            throw new Error("Not a data URI.");
        }
        let base64Idx = dataUri.indexOf("base64,");
        if (base64Idx != -1) {
            base64Idx += "base64,".length;
            return atob(dataUri.substr(base64Idx));
        }
        else {
            return dataUri.substr(dataUri.indexOf(",") + 1);
        }
    }
    base64ToUint8Array(base64) {
        var binary_string = window.atob(base64);
        var len = binary_string.length;
        var bytes = new Uint8Array(len);
        for (var i = 0; i < len; i++) {
            bytes[i] = binary_string.charCodeAt(i);
        }
        return bytes;
    }
    dataUriToUint8Array(dataUri) {
        if (!dataUri.startsWith("data:")) {
            throw new Error("Not a data URI.");
        }
        let base64Idx = dataUri.indexOf("base64,");
        if (base64Idx == -1)
            throw new Error("Not a binary data URI.");
        base64Idx += "base64,".length;
        return this.base64ToUint8Array(dataUri.substr(base64Idx));
    }
    downloadText(url, success, error) {
        if (this.start(url, success, error))
            return;
        const rawDataUri = this.rawDataUris[url];
        // we assume if a "." is included in a raw data uri, it is used to rewrite an asset URL
        if (rawDataUri && !rawDataUri.includes(".")) {
            try {
                this.finish(url, 200, this.dataUriToString(rawDataUri));
            }
            catch (e) {
                this.finish(url, 400, JSON.stringify(e));
            }
            return;
        }
        let request = new XMLHttpRequest();
        request.overrideMimeType("text/html");
        request.open("GET", rawDataUri ? rawDataUri : url, true);
        let done = () => {
            this.finish(url, request.status, request.responseText);
        };
        request.onload = done;
        request.onerror = done;
        request.send();
    }
    downloadJson(url, success, error) {
        this.downloadText(url, (data) => {
            success(JSON.parse(data));
        }, error);
    }
    downloadBinary(url, success, error) {
        if (this.start(url, success, error))
            return;
        const rawDataUri = this.rawDataUris[url];
        // we assume if a "." is included in a raw data uri, it is used to rewrite an asset URL
        if (rawDataUri && !rawDataUri.includes(".")) {
            try {
                this.finish(url, 200, this.dataUriToUint8Array(rawDataUri));
            }
            catch (e) {
                this.finish(url, 400, JSON.stringify(e));
            }
            return;
        }
        let request = new XMLHttpRequest();
        request.open("GET", rawDataUri ? rawDataUri : url, true);
        request.responseType = "arraybuffer";
        let onerror = () => {
            this.finish(url, request.status, request.response);
        };
        request.onload = () => {
            if (request.status == 200 || request.status == 0)
                this.finish(url, 200, new Uint8Array(request.response));
            else
                onerror();
        };
        request.onerror = onerror;
        request.send();
    }
    start(url, success, error) {
        let callbacks = this.callbacks[url];
        try {
            if (callbacks)
                return true;
            this.callbacks[url] = callbacks = [];
        }
        finally {
            callbacks.push(success, error);
        }
    }
    finish(url, status, data) {
        let callbacks = this.callbacks[url];
        delete this.callbacks[url];
        let args = status == 200 || status == 0 ? [data] : [status, data];
        for (let i = args.length - 1, n = callbacks.length; i < n; i += 2)
            callbacks[i].apply(null, args);
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiQXNzZXRNYW5hZ2VyQmFzZS5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3NyYy9Bc3NldE1hbmFnZXJCYXNlLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiJBQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7K0VBMkIrRTtBQUcvRSxPQUFPLEVBQUUsWUFBWSxFQUFFLE1BQU0sbUJBQW1CLENBQUM7QUFHakQsTUFBTSxPQUFPLGdCQUFnQjtJQUNwQixVQUFVLEdBQVcsRUFBRSxDQUFDO0lBQ3hCLGFBQWEsQ0FBcUQ7SUFDbEUsVUFBVSxDQUFhO0lBQ3ZCLEtBQUssQ0FBYTtJQUNsQixNQUFNLEdBQXNCLEVBQUUsQ0FBQztJQUMvQixNQUFNLEdBQUcsQ0FBQyxDQUFDO0lBQ1gsTUFBTSxHQUFHLENBQUMsQ0FBQztJQUVuQixZQUFhLGFBQWlFLEVBQUUsYUFBcUIsRUFBRSxFQUFFLFVBQVUsR0FBRyxJQUFJLFVBQVUsRUFBRSxFQUFFLEtBQUssR0FBRyxJQUFJLFVBQVUsRUFBRTtRQUMvSixJQUFJLENBQUMsYUFBYSxHQUFHLGFBQWEsQ0FBQztRQUNuQyxJQUFJLENBQUMsVUFBVSxHQUFHLFVBQVUsQ0FBQztRQUM3QixJQUFJLENBQUMsVUFBVSxHQUFHLFVBQVUsQ0FBQztRQUM3QixJQUFJLENBQUMsS0FBSyxHQUFHLEtBQUssQ0FBQztJQUNwQixDQUFDO0lBRU8sS0FBSyxDQUFFLElBQVk7UUFDMUIsSUFBSSxDQUFDLE1BQU0sRUFBRSxDQUFDO1FBQ2QsT0FBTyxJQUFJLENBQUMsVUFBVSxHQUFHLElBQUksQ0FBQztJQUMvQixDQUFDO0lBRU8sT0FBTyxDQUFFLFFBQTJDLEVBQUUsSUFBWSxFQUFFLEtBQVU7UUFDckYsSUFBSSxDQUFDLE1BQU0sRUFBRSxDQUFDO1FBQ2QsSUFBSSxDQUFDLE1BQU0sRUFBRSxDQUFDO1FBQ2QsSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLENBQUMsSUFBSSxDQUFDLEdBQUcsS0FBSyxDQUFDO1FBQ2hDLElBQUksQ0FBQyxLQUFLLENBQUMsY0FBYyxDQUFDLElBQUksQ0FBQyxHQUFHLENBQUMsSUFBSSxDQUFDLEtBQUssQ0FBQyxjQUFjLENBQUMsSUFBSSxDQUFDLElBQUksQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDO1FBQzdFLElBQUksUUFBUTtZQUFFLFFBQVEsQ0FBQyxJQUFJLEVBQUUsS0FBSyxDQUFDLENBQUM7SUFDckMsQ0FBQztJQUVPLEtBQUssQ0FBRSxRQUFpRCxFQUFFLElBQVksRUFBRSxPQUFlO1FBQzlGLElBQUksQ0FBQyxNQUFNLEVBQUUsQ0FBQztRQUNkLElBQUksQ0FBQyxNQUFNLEVBQUUsQ0FBQztRQUNkLElBQUksQ0FBQyxNQUFNLENBQUMsSUFBSSxDQUFDLEdBQUcsT0FBTyxDQUFDO1FBQzVCLElBQUksUUFBUTtZQUFFLFFBQVEsQ0FBQyxJQUFJLEVBQUUsT0FBTyxDQUFDLENBQUM7SUFDdkMsQ0FBQztJQUVELE9BQU87UUFDTixJQUFJLE9BQU8sR0FBRyxJQUFJLE9BQU8sQ0FBQyxDQUFDLE9BQWlELEVBQUUsTUFBMkMsRUFBRSxFQUFFO1lBQzVILElBQUksS0FBSyxHQUFHLEdBQUcsRUFBRTtnQkFDaEIsSUFBSSxJQUFJLENBQUMsaUJBQWlCLEVBQUUsRUFBRSxDQUFDO29CQUM5QixJQUFJLElBQUksQ0FBQyxTQUFTLEVBQUU7d0JBQUUsTUFBTSxDQUFDLElBQUksQ0FBQyxNQUFNLENBQUMsQ0FBQzs7d0JBQ3JDLE9BQU8sQ0FBQyxJQUFJLENBQUMsQ0FBQztvQkFDbkIsT0FBTztnQkFDUixDQUFDO2dCQUNELHFCQUFxQixDQUFDLEtBQUssQ0FBQyxDQUFDO1lBQzlCLENBQUMsQ0FBQTtZQUNELHFCQUFxQixDQUFDLEtBQUssQ0FBQyxDQUFDO1FBQzlCLENBQUMsQ0FBQyxDQUFDO1FBQ0gsT0FBTyxPQUFPLENBQUM7SUFDaEIsQ0FBQztJQUVELGFBQWEsQ0FBRSxJQUFZLEVBQUUsSUFBWTtRQUN4QyxJQUFJLENBQUMsVUFBVSxDQUFDLFdBQVcsQ0FBQyxJQUFJLENBQUMsVUFBVSxHQUFHLElBQUksQ0FBQyxHQUFHLElBQUksQ0FBQztJQUM1RCxDQUFDO0lBRUQsVUFBVSxDQUFFLElBQVksRUFDdkIsVUFBc0QsR0FBRyxFQUFFLEdBQUcsQ0FBQyxFQUMvRCxRQUFpRCxHQUFHLEVBQUUsR0FBRyxDQUFDO1FBQzFELElBQUksR0FBRyxJQUFJLENBQUMsS0FBSyxDQUFDLElBQUksQ0FBQyxDQUFDO1FBRXhCLElBQUksSUFBSSxDQUFDLFdBQVcsQ0FBQyxJQUFJLEVBQUUsT0FBTyxFQUFFLEtBQUssQ0FBQztZQUFFLE9BQU87UUFFbkQsSUFBSSxDQUFDLEtBQUssQ0FBQyxZQUFZLENBQUMsSUFBSSxDQUFDLEdBQUcsSUFBSSxPQUFPLENBQU0sQ0FBQyxPQUFPLEVBQUUsTUFBTSxFQUFFLEVBQUU7WUFDcEUsSUFBSSxDQUFDLFVBQVUsQ0FBQyxjQUFjLENBQUMsSUFBSSxFQUFFLENBQUMsSUFBZ0IsRUFBUSxFQUFFO2dCQUMvRCxJQUFJLENBQUMsT0FBTyxDQUFDLE9BQU8sRUFBRSxJQUFJLEVBQUUsSUFBSSxDQUFDLENBQUM7Z0JBQ2xDLE9BQU8sQ0FBQyxJQUFJLENBQUMsQ0FBQztZQUNmLENBQUMsRUFBRSxDQUFDLE1BQWMsRUFBRSxZQUFvQixFQUFRLEVBQUU7Z0JBQ2pELE1BQU0sUUFBUSxHQUFHLHdCQUF3QixJQUFJLFlBQVksTUFBTSxLQUFLLFlBQVksRUFBRSxDQUFDO2dCQUNuRixJQUFJLENBQUMsS0FBSyxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsUUFBUSxDQUFDLENBQUM7Z0JBQ2xDLE1BQU0sQ0FBQyxRQUFRLENBQUMsQ0FBQztZQUNsQixDQUFDLENBQUMsQ0FBQztRQUNKLENBQUMsQ0FBQyxDQUFDO0lBQ0osQ0FBQztJQUVELFFBQVEsQ0FBRSxJQUFZLEVBQ3JCLFVBQWdELEdBQUcsRUFBRSxHQUFHLENBQUMsRUFDekQsUUFBaUQsR0FBRyxFQUFFLEdBQUcsQ0FBQztRQUMxRCxJQUFJLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxJQUFJLENBQUMsQ0FBQztRQUV4QixJQUFJLENBQUMsVUFBVSxDQUFDLFlBQVksQ0FBQyxJQUFJLEVBQUUsQ0FBQyxJQUFZLEVBQVEsRUFBRTtZQUN6RCxJQUFJLENBQUMsT0FBTyxDQUFDLE9BQU8sRUFBRSxJQUFJLEVBQUUsSUFBSSxDQUFDLENBQUM7UUFDbkMsQ0FBQyxFQUFFLENBQUMsTUFBYyxFQUFFLFlBQW9CLEVBQVEsRUFBRTtZQUNqRCxJQUFJLENBQUMsS0FBSyxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsc0JBQXNCLElBQUksWUFBWSxNQUFNLEtBQUssWUFBWSxFQUFFLENBQUMsQ0FBQztRQUMxRixDQUFDLENBQUMsQ0FBQztJQUNKLENBQUM7SUFFRCxRQUFRLENBQUUsSUFBWSxFQUNyQixVQUFrRCxHQUFHLEVBQUUsR0FBRyxDQUFDLEVBQzNELFFBQWlELEdBQUcsRUFBRSxHQUFHLENBQUM7UUFDMUQsSUFBSSxHQUFHLElBQUksQ0FBQyxLQUFLLENBQUMsSUFBSSxDQUFDLENBQUM7UUFFeEIsSUFBSSxJQUFJLENBQUMsV0FBVyxDQUFDLElBQUksRUFBRSxPQUFPLEVBQUUsS0FBSyxDQUFDO1lBQUUsT0FBTztRQUVuRCxJQUFJLENBQUMsS0FBSyxDQUFDLFlBQVksQ0FBQyxJQUFJLENBQUMsR0FBRyxJQUFJLE9BQU8sQ0FBTSxDQUFDLE9BQU8sRUFBRSxNQUFNLEVBQUUsRUFBRTtZQUNwRSxJQUFJLENBQUMsVUFBVSxDQUFDLFlBQVksQ0FBQyxJQUFJLEVBQUUsQ0FBQyxJQUFZLEVBQVEsRUFBRTtnQkFDekQsSUFBSSxDQUFDLE9BQU8sQ0FBQyxPQUFPLEVBQUUsSUFBSSxFQUFFLElBQUksQ0FBQyxDQUFDO2dCQUNsQyxPQUFPLENBQUMsSUFBSSxDQUFDLENBQUM7WUFDZixDQUFDLEVBQUUsQ0FBQyxNQUFjLEVBQUUsWUFBb0IsRUFBUSxFQUFFO2dCQUNqRCxNQUFNLFFBQVEsR0FBRyxzQkFBc0IsSUFBSSxZQUFZLE1BQU0sS0FBSyxZQUFZLEVBQUUsQ0FBQztnQkFDakYsSUFBSSxDQUFDLEtBQUssQ0FBQyxLQUFLLEVBQUUsSUFBSSxFQUFFLFFBQVEsQ0FBQyxDQUFDO2dCQUNsQyxNQUFNLENBQUMsUUFBUSxDQUFDLENBQUM7WUFDbEIsQ0FBQyxDQUFDLENBQUM7UUFDSixDQUFDLENBQUMsQ0FBQztJQUNKLENBQUM7SUFFRCxXQUFXLENBQUUsSUFBWSxFQUN4QixVQUE2QyxHQUFHLEVBQUUsR0FBRyxDQUFDLEVBQ3RELFFBQWlELEdBQUcsRUFBRSxHQUFHLENBQUM7UUFDMUQsTUFBTSxZQUFZLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxZQUFZLENBQUMsSUFBSSxDQUFDLENBQUM7UUFDbkQsTUFBTSxzQkFBc0IsR0FBRyxZQUFZLEtBQUssU0FBUyxDQUFDO1FBQzFELElBQUksc0JBQXNCLEVBQUUsQ0FBQztZQUM1QixJQUFJLENBQUMsS0FBSyxDQUFDLFlBQVksQ0FBQyxJQUFJLENBQUMsR0FBRyxZQUFZO2lCQUMxQyxJQUFJLENBQUMsSUFBSSxDQUFDLEVBQUU7Z0JBQ1osd0RBQXdEO2dCQUN4RCx5RkFBeUY7Z0JBQ3pGLElBQUksR0FBRyxDQUFDLElBQUksWUFBWSxLQUFLLElBQUksSUFBSSxZQUFZLFdBQVcsQ0FBQyxDQUFDLENBQUMsQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLElBQUksQ0FBQyxDQUFDLENBQUMsQ0FBQyxJQUFJLENBQUM7Z0JBQ2hHLElBQUksQ0FBQyxPQUFPLENBQUMsT0FBTyxFQUFFLElBQUksRUFBRSxJQUFJLENBQUMsQ0FBQztnQkFDbEMsT0FBTyxJQUFJLENBQUM7WUFDYixDQUFDLENBQUM7aUJBQ0QsS0FBSyxDQUFDLFFBQVEsQ0FBQyxFQUFFLENBQUMsSUFBSSxDQUFDLEtBQUssQ0FBQyxLQUFLLEVBQUUsSUFBSSxFQUFFLFFBQVEsQ0FBQyxDQUFDLENBQUM7UUFDeEQsQ0FBQztRQUNELE9BQU8sc0JBQXNCLENBQUM7SUFDL0IsQ0FBQztJQUVELFdBQVcsQ0FBRSxJQUFZLEVBQ3hCLFVBQW9ELEdBQUcsRUFBRSxHQUFHLENBQUMsRUFDN0QsUUFBaUQsR0FBRyxFQUFFLEdBQUcsQ0FBQztRQUUxRCxJQUFJLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxJQUFJLENBQUMsQ0FBQztRQUV4QixJQUFJLElBQUksQ0FBQyxXQUFXLENBQUMsSUFBSSxFQUFFLE9BQU8sRUFBRSxLQUFLLENBQUM7WUFBRSxPQUFPO1FBRW5ELElBQUksQ0FBQyxLQUFLLENBQUMsWUFBWSxDQUFDLElBQUksQ0FBQyxHQUFHLElBQUksT0FBTyxDQUFNLENBQUMsT0FBTyxFQUFFLE1BQU0sRUFBRSxFQUFFO1lBQ3BFLElBQUksU0FBUyxHQUFHLENBQUMsQ0FBQyxDQUFDLE9BQU8sTUFBTSxLQUFLLFdBQVcsSUFBSSxPQUFPLFNBQVMsS0FBSyxXQUFXLElBQUksTUFBTSxDQUFDLFFBQVEsQ0FBQyxDQUFDO1lBQ3pHLElBQUksV0FBVyxHQUFHLENBQUMsU0FBUyxDQUFDLENBQUMsMkNBQTJDO1lBQ3pFLElBQUksV0FBVyxFQUFFLENBQUM7Z0JBQ2pCLEtBQUssQ0FBQyxJQUFJLEVBQUUsRUFBRSxJQUFJLEVBQWUsTUFBTSxFQUFFLENBQUMsQ0FBQyxJQUFJLENBQUMsQ0FBQyxRQUFRLEVBQUUsRUFBRTtvQkFDNUQsSUFBSSxRQUFRLENBQUMsRUFBRTt3QkFBRSxPQUFPLFFBQVEsQ0FBQyxJQUFJLEVBQUUsQ0FBQztvQkFDeEMsTUFBTSxRQUFRLEdBQUcsd0JBQXdCLElBQUksRUFBRSxDQUFDO29CQUNoRCxJQUFJLENBQUMsS0FBSyxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsd0JBQXdCLElBQUksRUFBRSxDQUFDLENBQUM7b0JBQ3hELE1BQU0sQ0FBQyxRQUFRLENBQUMsQ0FBQztnQkFDbEIsQ0FBQyxDQUFDLENBQUMsSUFBSSxDQUFDLENBQUMsSUFBSSxFQUFFLEVBQUU7b0JBQ2hCLE9BQU8sSUFBSSxDQUFDLENBQUMsQ0FBQyxpQkFBaUIsQ0FBQyxJQUFJLEVBQUUsRUFBRSxnQkFBZ0IsRUFBRSxNQUFNLEVBQUUsb0JBQW9CLEVBQUUsTUFBTSxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUMsSUFBSSxDQUFDO2dCQUMxRyxDQUFDLENBQUMsQ0FBQyxJQUFJLENBQUMsQ0FBQyxNQUFNLEVBQUUsRUFBRTtvQkFDbEIsSUFBSSxNQUFNLEVBQUUsQ0FBQzt3QkFDWixNQUFNLE9BQU8sR0FBRyxJQUFJLENBQUMsYUFBYSxDQUFDLElBQUksRUFBRSxNQUFNLENBQUMsQ0FBQzt3QkFDakQsSUFBSSxDQUFDLE9BQU8sQ0FBQyxPQUFPLEVBQUUsSUFBSSxFQUFFLE9BQU8sQ0FBQyxDQUFDO3dCQUNyQyxPQUFPLENBQUMsT0FBTyxDQUFDLENBQUM7b0JBQ2xCLENBQUM7b0JBQUEsQ0FBQztnQkFDSCxDQUFDLENBQUMsQ0FBQztZQUNKLENBQUM7aUJBQU0sQ0FBQztnQkFDUCxJQUFJLEtBQUssR0FBRyxJQUFJLEtBQUssRUFBRSxDQUFDO2dCQUN4QixLQUFLLENBQUMsV0FBVyxHQUFHLFdBQVcsQ0FBQztnQkFDaEMsS0FBSyxDQUFDLE1BQU0sR0FBRyxHQUFHLEVBQUU7b0JBQ25CLE1BQU0sT0FBTyxHQUFHLElBQUksQ0FBQyxhQUFhLENBQUMsSUFBSSxFQUFFLEtBQUssQ0FBQyxDQUFDO29CQUNoRCxJQUFJLENBQUMsT0FBTyxDQUFDLE9BQU8sRUFBRSxJQUFJLEVBQUUsT0FBTyxDQUFDLENBQUM7b0JBQ3JDLE9BQU8sQ0FBQyxPQUFPLENBQUMsQ0FBQztnQkFDbEIsQ0FBQyxDQUFDO2dCQUNGLEtBQUssQ0FBQyxPQUFPLEdBQUcsR0FBRyxFQUFFO29CQUNwQixNQUFNLFFBQVEsR0FBRyx3QkFBd0IsSUFBSSxFQUFFLENBQUM7b0JBQ2hELElBQUksQ0FBQyxLQUFLLENBQUMsS0FBSyxFQUFFLElBQUksRUFBRSxRQUFRLENBQUMsQ0FBQztvQkFDbEMsTUFBTSxDQUFDLFFBQVEsQ0FBQyxDQUFDO2dCQUNsQixDQUFDLENBQUM7Z0JBQ0YsSUFBSSxJQUFJLENBQUMsVUFBVSxDQUFDLFdBQVcsQ0FBQyxJQUFJLENBQUM7b0JBQUUsSUFBSSxHQUFHLElBQUksQ0FBQyxVQUFVLENBQUMsV0FBVyxDQUFDLElBQUksQ0FBQyxDQUFDO2dCQUNoRixLQUFLLENBQUMsR0FBRyxHQUFHLElBQUksQ0FBQztZQUNsQixDQUFDO1FBQ0YsQ0FBQyxDQUFDLENBQUM7SUFDSixDQUFDO0lBRUQsZ0JBQWdCLENBQUUsSUFBWSxFQUM3QixVQUF1RCxHQUFHLEVBQUUsR0FBRyxDQUFDLEVBQ2hFLFFBQWlELEdBQUcsRUFBRSxHQUFHLENBQUMsRUFDMUQsU0FBeUM7UUFFekMsSUFBSSxLQUFLLEdBQUcsSUFBSSxDQUFDLFdBQVcsQ0FBQyxHQUFHLENBQUMsQ0FBQztRQUNsQyxJQUFJLE1BQU0sR0FBRyxLQUFLLElBQUksQ0FBQyxDQUFDLENBQUMsQ0FBQyxJQUFJLENBQUMsU0FBUyxDQUFDLENBQUMsRUFBRSxLQUFLLEdBQUcsQ0FBQyxDQUFDLENBQUMsQ0FBQyxDQUFDLEVBQUUsQ0FBQztRQUM1RCxJQUFJLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxJQUFJLENBQUMsQ0FBQztRQUV4QixJQUFJLElBQUksQ0FBQyxXQUFXLENBQUMsSUFBSSxFQUFFLE9BQU8sRUFBRSxLQUFLLENBQUM7WUFBRSxPQUFPO1FBRW5ELElBQUksQ0FBQyxLQUFLLENBQUMsWUFBWSxDQUFDLElBQUksQ0FBQyxHQUFHLElBQUksT0FBTyxDQUFNLENBQUMsT0FBTyxFQUFFLE1BQU0sRUFBRSxFQUFFO1lBQ3BFLElBQUksQ0FBQyxVQUFVLENBQUMsWUFBWSxDQUFDLElBQUksRUFBRSxDQUFDLFNBQWlCLEVBQVEsRUFBRTtnQkFDOUQsSUFBSSxDQUFDO29CQUNKLE1BQU0sS0FBSyxHQUFHLElBQUksQ0FBQyxrQkFBa0IsQ0FBQyxJQUFJLEVBQUUsU0FBUyxDQUFDLENBQUM7b0JBQ3ZELElBQUksTUFBTSxHQUFHLEtBQUssQ0FBQyxLQUFLLENBQUMsTUFBTSxFQUFFLEtBQUssR0FBRyxLQUFLLENBQUM7b0JBRS9DLElBQUksTUFBTSxLQUFLLENBQUMsRUFBRSxDQUFDO3dCQUNsQixJQUFJLENBQUMsT0FBTyxDQUFDLE9BQU8sRUFBRSxJQUFJLEVBQUUsS0FBSyxDQUFDLENBQUM7d0JBQ25DLE9BQU8sQ0FBQyxLQUFLLENBQUMsQ0FBQzt3QkFDZixPQUFPO29CQUNSLENBQUM7b0JBRUQsS0FBSyxJQUFJLElBQUksSUFBSSxLQUFLLENBQUMsS0FBSyxFQUFFLENBQUM7d0JBQzlCLElBQUksQ0FBQyxXQUFXLENBQUMsQ0FBQyxTQUFTLENBQUMsQ0FBQyxDQUFDLE1BQU0sR0FBRyxJQUFJLENBQUMsSUFBSSxDQUFDLENBQUMsQ0FBQyxTQUFTLENBQUMsSUFBSSxDQUFDLElBQUssQ0FBQyxFQUN2RSxDQUFDLFNBQWlCLEVBQUUsT0FBZ0IsRUFBRSxFQUFFOzRCQUN2QyxJQUFJLENBQUMsS0FBSyxFQUFFLENBQUM7Z0NBQ1osSUFBSSxDQUFDLFVBQVUsQ0FBQyxPQUFPLENBQUMsQ0FBQztnQ0FDekIsSUFBSSxFQUFFLE1BQU0sSUFBSSxDQUFDLEVBQUUsQ0FBQztvQ0FDbkIsSUFBSSxDQUFDLE9BQU8sQ0FBQyxPQUFPLEVBQUUsSUFBSSxFQUFFLEtBQUssQ0FBQyxDQUFDO29DQUNuQyxPQUFPLENBQUMsS0FBSyxDQUFDLENBQUM7Z0NBQ2hCLENBQUM7NEJBQ0YsQ0FBQzt3QkFDRixDQUFDLEVBQ0QsQ0FBQyxTQUFpQixFQUFFLE9BQWUsRUFBRSxFQUFFOzRCQUN0QyxJQUFJLENBQUMsS0FBSyxFQUFFLENBQUM7Z0NBQ1osTUFBTSxRQUFRLEdBQUcseUJBQXlCLElBQUksZ0JBQWdCLFNBQVMsRUFBRSxDQUFDO2dDQUMxRSxJQUFJLENBQUMsS0FBSyxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsUUFBUSxDQUFDLENBQUM7Z0NBQ2xDLE1BQU0sQ0FBQyxRQUFRLENBQUMsQ0FBQzs0QkFDbEIsQ0FBQzs0QkFDRCxLQUFLLEdBQUcsSUFBSSxDQUFDO3dCQUNkLENBQUMsQ0FDRCxDQUFDO29CQUNILENBQUM7Z0JBQ0YsQ0FBQztnQkFBQyxPQUFPLENBQUMsRUFBRSxDQUFDO29CQUNaLE1BQU0sUUFBUSxHQUFHLGdDQUFnQyxJQUFJLEtBQU0sQ0FBUyxDQUFDLE9BQU8sRUFBRSxDQUFDO29CQUMvRSxJQUFJLENBQUMsS0FBSyxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsUUFBUSxDQUFDLENBQUM7b0JBQ2xDLE1BQU0sQ0FBQyxRQUFRLENBQUMsQ0FBQztnQkFDbEIsQ0FBQztZQUNGLENBQUMsRUFBRSxDQUFDLE1BQWMsRUFBRSxZQUFvQixFQUFRLEVBQUU7Z0JBQ2pELE1BQU0sUUFBUSxHQUFHLCtCQUErQixJQUFJLFlBQVksTUFBTSxLQUFLLFlBQVksRUFBRSxDQUFDO2dCQUMxRixJQUFJLENBQUMsS0FBSyxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsUUFBUSxDQUFDLENBQUM7Z0JBQ2xDLE1BQU0sQ0FBQyxRQUFRLENBQUMsQ0FBQztZQUNsQixDQUFDLENBQUMsQ0FBQztRQUNKLENBQUMsQ0FBQyxDQUFDO0lBQ0osQ0FBQztJQUVELDZCQUE2QixDQUFFLElBQVksRUFDMUMsVUFBdUQsR0FBRyxFQUFFLEdBQUcsQ0FBQyxFQUNoRSxRQUFpRCxHQUFHLEVBQUUsR0FBRyxDQUFDLEVBQzFELFNBQXlDO1FBRXpDLElBQUksR0FBRyxJQUFJLENBQUMsS0FBSyxDQUFDLElBQUksQ0FBQyxDQUFDO1FBRXhCLElBQUksSUFBSSxDQUFDLFdBQVcsQ0FBQyxJQUFJLEVBQUUsT0FBTyxFQUFFLEtBQUssQ0FBQztZQUFFLE9BQU87UUFFbkQsSUFBSSxDQUFDLEtBQUssQ0FBQyxZQUFZLENBQUMsSUFBSSxDQUFDLEdBQUcsSUFBSSxPQUFPLENBQU0sQ0FBQyxPQUFPLEVBQUUsTUFBTSxFQUFFLEVBQUU7WUFDcEUsSUFBSSxDQUFDLFVBQVUsQ0FBQyxZQUFZLENBQUMsSUFBSSxFQUFFLENBQUMsU0FBaUIsRUFBUSxFQUFFO2dCQUM5RCxJQUFJLENBQUM7b0JBQ0osTUFBTSxLQUFLLEdBQUcsSUFBSSxDQUFDLGtCQUFrQixDQUFDLElBQUksRUFBRSxTQUFTLENBQUMsQ0FBQztvQkFDdkQsSUFBSSxDQUFDLE9BQU8sQ0FBQyxPQUFPLEVBQUUsSUFBSSxFQUFFLEtBQUssQ0FBQyxDQUFDO29CQUNuQyxPQUFPLENBQUMsS0FBSyxDQUFDLENBQUM7Z0JBQ2hCLENBQUM7Z0JBQUMsT0FBTyxDQUFDLEVBQUUsQ0FBQztvQkFDWixNQUFNLFFBQVEsR0FBRyxnQ0FBZ0MsSUFBSSxLQUFNLENBQVMsQ0FBQyxPQUFPLEVBQUUsQ0FBQztvQkFDL0UsSUFBSSxDQUFDLEtBQUssQ0FBQyxLQUFLLEVBQUUsSUFBSSxFQUFFLFFBQVEsQ0FBQyxDQUFDO29CQUNsQyxNQUFNLENBQUMsUUFBUSxDQUFDLENBQUM7Z0JBQ2xCLENBQUM7WUFDRixDQUFDLEVBQUUsQ0FBQyxNQUFjLEVBQUUsWUFBb0IsRUFBUSxFQUFFO2dCQUNqRCxNQUFNLFFBQVEsR0FBRywrQkFBK0IsSUFBSSxZQUFZLE1BQU0sS0FBSyxZQUFZLEVBQUUsQ0FBQztnQkFDMUYsSUFBSSxDQUFDLEtBQUssQ0FBQyxLQUFLLEVBQUUsSUFBSSxFQUFFLFFBQVEsQ0FBQyxDQUFDO2dCQUNsQyxNQUFNLENBQUMsUUFBUSxDQUFDLENBQUM7WUFDbEIsQ0FBQyxDQUFDLENBQUM7UUFDSixDQUFDLENBQUMsQ0FBQztJQUNKLENBQUM7SUFFRCx3Q0FBd0M7SUFDeEMsS0FBSyxDQUFDLGVBQWUsQ0FBRSxJQUFZO1FBQ2xDLE9BQU8sSUFBSSxPQUFPLENBQUMsQ0FBQyxPQUFPLEVBQUUsTUFBTSxFQUFFLEVBQUU7WUFDdEMsSUFBSSxDQUFDLFVBQVUsQ0FBQyxJQUFJLEVBQ25CLENBQUMsQ0FBQyxFQUFFLE1BQU0sRUFBRSxFQUFFLENBQUMsT0FBTyxDQUFDLE1BQU0sQ0FBQyxFQUM5QixDQUFDLENBQUMsRUFBRSxPQUFPLEVBQUUsRUFBRSxDQUFDLE1BQU0sQ0FBQyxPQUFPLENBQUMsQ0FDL0IsQ0FBQztRQUNILENBQUMsQ0FBQyxDQUFDO0lBQ0osQ0FBQztJQUVELEtBQUssQ0FBQyxhQUFhLENBQUUsSUFBWTtRQUNoQyxPQUFPLElBQUksT0FBTyxDQUFDLENBQUMsT0FBTyxFQUFFLE1BQU0sRUFBRSxFQUFFO1lBQ3RDLElBQUksQ0FBQyxRQUFRLENBQUMsSUFBSSxFQUNqQixDQUFDLENBQUMsRUFBRSxNQUFNLEVBQUUsRUFBRSxDQUFDLE9BQU8sQ0FBQyxNQUFNLENBQUMsRUFDOUIsQ0FBQyxDQUFDLEVBQUUsT0FBTyxFQUFFLEVBQUUsQ0FBQyxNQUFNLENBQUMsT0FBTyxDQUFDLENBQy9CLENBQUM7UUFDSCxDQUFDLENBQUMsQ0FBQztJQUNKLENBQUM7SUFFRCxLQUFLLENBQUMsZ0JBQWdCLENBQUUsSUFBWTtRQUNuQyxPQUFPLElBQUksT0FBTyxDQUFVLENBQUMsT0FBTyxFQUFFLE1BQU0sRUFBRSxFQUFFO1lBQy9DLElBQUksQ0FBQyxXQUFXLENBQUMsSUFBSSxFQUNwQixDQUFDLENBQUMsRUFBRSxPQUFPLEVBQUUsRUFBRSxDQUFDLE9BQU8sQ0FBQyxPQUFPLENBQUMsRUFDaEMsQ0FBQyxDQUFDLEVBQUUsT0FBTyxFQUFFLEVBQUUsQ0FBQyxNQUFNLENBQUMsT0FBTyxDQUFDLENBQy9CLENBQUM7UUFDSCxDQUFDLENBQUMsQ0FBQztJQUNKLENBQUM7SUFFRCxLQUFLLENBQUMscUJBQXFCLENBQUUsSUFBWTtRQUN4QyxPQUFPLElBQUksT0FBTyxDQUFDLENBQUMsT0FBTyxFQUFFLE1BQU0sRUFBRSxFQUFFO1lBQ3RDLElBQUksQ0FBQyxnQkFBZ0IsQ0FBQyxJQUFJLEVBQ3pCLENBQUMsQ0FBQyxFQUFFLEtBQUssRUFBRSxFQUFFLENBQUMsT0FBTyxDQUFDLEtBQUssQ0FBQyxFQUM1QixDQUFDLENBQUMsRUFBRSxPQUFPLEVBQUUsRUFBRSxDQUFDLE1BQU0sQ0FBQyxPQUFPLENBQUMsQ0FDL0IsQ0FBQztRQUNILENBQUMsQ0FBQyxDQUFDO0lBQ0osQ0FBQztJQUVELEtBQUssQ0FBQyxrQ0FBa0MsQ0FBRSxJQUFZO1FBQ3JELE9BQU8sSUFBSSxPQUFPLENBQWUsQ0FBQyxPQUFPLEVBQUUsTUFBTSxFQUFFLEVBQUU7WUFDcEQsSUFBSSxDQUFDLDZCQUE2QixDQUFDLElBQUksRUFDdEMsQ0FBQyxDQUFDLEVBQUUsS0FBSyxFQUFFLEVBQUUsQ0FBQyxPQUFPLENBQUMsS0FBSyxDQUFDLEVBQzVCLENBQUMsQ0FBQyxFQUFFLE9BQU8sRUFBRSxFQUFFLENBQUMsTUFBTSxDQUFDLE9BQU8sQ0FBQyxDQUMvQixDQUFDO1FBQ0gsQ0FBQyxDQUFDLENBQUM7SUFDSixDQUFDO0lBRUQsUUFBUSxDQUFFLEtBQWlCO1FBQzFCLElBQUksQ0FBQyxLQUFLLEdBQUcsS0FBSyxDQUFDO0lBQ3BCLENBQUM7SUFFRCxHQUFHLENBQUUsSUFBWTtRQUNoQixPQUFPLElBQUksQ0FBQyxLQUFLLENBQUMsTUFBTSxDQUFDLElBQUksQ0FBQyxVQUFVLEdBQUcsSUFBSSxDQUFDLENBQUM7SUFDbEQsQ0FBQztJQUVELE9BQU8sQ0FBRSxJQUFZO1FBQ3BCLElBQUksR0FBRyxJQUFJLENBQUMsVUFBVSxHQUFHLElBQUksQ0FBQztRQUM5QixJQUFJLEtBQUssR0FBRyxJQUFJLENBQUMsS0FBSyxDQUFDLE1BQU0sQ0FBQyxJQUFJLENBQUMsQ0FBQztRQUNwQyxJQUFJLEtBQUs7WUFBRSxPQUFPLEtBQUssQ0FBQztRQUN4QixJQUFJLEtBQUssR0FBRyxJQUFJLENBQUMsTUFBTSxDQUFDLElBQUksQ0FBQyxDQUFDO1FBQzlCLE1BQU0sS0FBSyxDQUFDLG1CQUFtQixHQUFHLElBQUksR0FBRyxDQUFDLEtBQUssQ0FBQyxDQUFDLENBQUMsSUFBSSxHQUFHLEtBQUssQ0FBQyxDQUFDLENBQUMsRUFBRSxDQUFDLENBQUMsQ0FBQztJQUN2RSxDQUFDO0lBRUQsTUFBTSxDQUFFLElBQVk7UUFDbkIsSUFBSSxHQUFHLElBQUksQ0FBQyxVQUFVLEdBQUcsSUFBSSxDQUFDO1FBQzlCLElBQUksS0FBSyxHQUFHLElBQUksQ0FBQyxLQUFLLENBQUMsTUFBTSxDQUFDLElBQUksQ0FBQyxDQUFDO1FBQ3BDLElBQUksS0FBSyxDQUFDLE9BQU87WUFBRSxLQUFLLENBQUMsT0FBTyxFQUFFLENBQUM7UUFDbkMsT0FBTyxJQUFJLENBQUMsS0FBSyxDQUFDLE1BQU0sQ0FBQyxJQUFJLENBQUMsQ0FBQztRQUMvQixPQUFPLElBQUksQ0FBQyxLQUFLLENBQUMsY0FBYyxDQUFDLElBQUksQ0FBQyxDQUFDO1FBQ3ZDLE9BQU8sSUFBSSxDQUFDLEtBQUssQ0FBQyxZQUFZLENBQUMsSUFBSSxDQUFDLENBQUM7UUFDckMsT0FBTyxLQUFLLENBQUM7SUFDZCxDQUFDO0lBRUQsU0FBUztRQUNSLEtBQUssSUFBSSxJQUFJLElBQUksSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLEVBQUUsQ0FBQztZQUNwQyxJQUFJLEtBQUssR0FBRyxJQUFJLENBQUMsS0FBSyxDQUFDLE1BQU0sQ0FBQyxJQUFJLENBQUMsQ0FBQztZQUNwQyxJQUFJLEtBQUssQ0FBQyxPQUFPO2dCQUFFLEtBQUssQ0FBQyxPQUFPLEVBQUUsQ0FBQztRQUNwQyxDQUFDO1FBQ0QsSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLEdBQUcsRUFBRSxDQUFDO1FBQ3ZCLElBQUksQ0FBQyxLQUFLLENBQUMsWUFBWSxHQUFHLEVBQUUsQ0FBQztRQUM3QixJQUFJLENBQUMsS0FBSyxDQUFDLGNBQWMsR0FBRyxFQUFFLENBQUM7SUFDaEMsQ0FBQztJQUVELGlCQUFpQjtRQUNoQixPQUFPLElBQUksQ0FBQyxNQUFNLElBQUksQ0FBQyxDQUFDO0lBQ3pCLENBQUM7SUFFRCxTQUFTO1FBQ1IsT0FBTyxJQUFJLENBQUMsTUFBTSxDQUFDO0lBQ3BCLENBQUM7SUFFRCxTQUFTO1FBQ1IsT0FBTyxJQUFJLENBQUMsTUFBTSxDQUFDO0lBQ3BCLENBQUM7SUFFRCxPQUFPO1FBQ04sSUFBSSxDQUFDLFNBQVMsRUFBRSxDQUFDO0lBQ2xCLENBQUM7SUFFRCxnREFBZ0Q7SUFDaEQsWUFBWSxDQUFFLElBQVk7UUFDekIsTUFBTSxLQUFLLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLENBQUMsSUFBSSxDQUFDLENBQUM7UUFDdEMsSUFBSSxLQUFLLFlBQVksWUFBWSxFQUFFLENBQUM7WUFDbkMsS0FBSyxDQUFDLE9BQU8sRUFBRSxDQUFDO1lBQ2hCLE9BQU87UUFDUixDQUFDO1FBQ0QsSUFBSSxDQUFDLG9CQUFvQixDQUFDLElBQUksQ0FBQyxDQUFDO0lBQ2pDLENBQUM7SUFFRCxTQUFTO1FBQ1IsT0FBTyxNQUFNLENBQUMsSUFBSSxDQUFDLElBQUksQ0FBQyxNQUFNLENBQUMsQ0FBQyxNQUFNLEdBQUcsQ0FBQyxDQUFDO0lBQzVDLENBQUM7SUFFRCxTQUFTO1FBQ1IsT0FBTyxJQUFJLENBQUMsTUFBTSxDQUFDO0lBQ3BCLENBQUM7SUFFTyxvQkFBb0IsQ0FBRSxJQUFZO1FBQ3pDLElBQUksSUFBSSxDQUFDLEtBQUssQ0FBQyxjQUFjLENBQUMsSUFBSSxDQUFDLEdBQUcsQ0FBQyxJQUFJLEVBQUUsSUFBSSxDQUFDLEtBQUssQ0FBQyxjQUFjLENBQUMsSUFBSSxDQUFDLEtBQUssQ0FBQyxFQUFFLENBQUM7WUFDcEYsT0FBTyxJQUFJLENBQUMsTUFBTSxDQUFDLElBQUksQ0FBQyxDQUFDO1FBQzFCLENBQUM7SUFDRixDQUFDO0lBRU8sa0JBQWtCLENBQUUsSUFBWSxFQUFFLFNBQWlCO1FBQzFELE1BQU0sS0FBSyxHQUFHLElBQUksWUFBWSxDQUFDLFNBQVMsQ0FBQyxDQUFDO1FBQzFDLEtBQUssQ0FBQyxPQUFPLEdBQUcsR0FBRyxFQUFFO1lBQ3BCLElBQUksSUFBSSxDQUFDLEtBQUssQ0FBQyxjQUFjLENBQUMsSUFBSSxDQUFDLElBQUksQ0FBQztnQkFBRSxPQUFPO1lBQ2pELElBQUksQ0FBQyxvQkFBb0IsQ0FBQyxJQUFJLENBQUMsQ0FBQztZQUNoQyxLQUFLLE1BQU0sSUFBSSxJQUFJLEtBQUssQ0FBQyxLQUFLLEVBQUUsQ0FBQztnQkFDaEMsSUFBSSxDQUFDLE9BQU8sRUFBRSxPQUFPLEVBQUUsQ0FBQztZQUN6QixDQUFDO1FBQ0YsQ0FBQyxDQUFBO1FBQ0QsT0FBTyxLQUFLLENBQUM7SUFDZCxDQUFDO0lBRU8sYUFBYSxDQUFFLElBQVksRUFBRSxLQUFxQztRQUN6RSxNQUFNLE9BQU8sR0FBRyxJQUFJLENBQUMsYUFBYSxDQUFDLEtBQUssQ0FBQyxDQUFDO1FBQzFDLE1BQU0sY0FBYyxHQUFHLE9BQU8sQ0FBQyxPQUFPLENBQUMsSUFBSSxDQUFDLE9BQU8sQ0FBQyxDQUFDO1FBQ3JELE9BQU8sQ0FBQyxPQUFPLEdBQUcsR0FBRyxFQUFFO1lBQ3RCLElBQUksSUFBSSxDQUFDLG9CQUFvQixDQUFDLElBQUksQ0FBQztnQkFBRSxjQUFjLEVBQUUsQ0FBQztRQUN2RCxDQUFDLENBQUE7UUFDRCxPQUFPLE9BQU8sQ0FBQztJQUNoQixDQUFDO0NBQ0Q7QUFFRCxNQUFNLE9BQU8sVUFBVTtJQUNmLE1BQU0sR0FBbUIsRUFBRSxDQUFDO0lBQzVCLGNBQWMsR0FBc0IsRUFBRSxDQUFDO0lBQ3ZDLFlBQVksR0FBNEIsRUFBRSxDQUFDO0lBRWxELE1BQU0sQ0FBQyxnQkFBZ0IsR0FBRyxJQUFJLEdBQUcsRUFBc0IsQ0FBQztJQUN4RCxNQUFNLENBQUMsUUFBUSxDQUFFLEVBQVU7UUFDMUIsTUFBTSxLQUFLLEdBQUcsVUFBVSxDQUFDLGdCQUFnQixDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsQ0FBQztRQUNsRCxJQUFJLEtBQUs7WUFBRSxPQUFPLEtBQUssQ0FBQztRQUV4QixNQUFNLFFBQVEsR0FBRyxJQUFJLFVBQVUsRUFBRSxDQUFDO1FBQ2xDLFVBQVUsQ0FBQyxnQkFBZ0IsQ0FBQyxHQUFHLENBQUMsRUFBRSxFQUFFLFFBQVEsQ0FBQyxDQUFDO1FBQzlDLE9BQU8sUUFBUSxDQUFDO0lBQ2pCLENBQUM7SUFFRCxLQUFLLENBQUMsUUFBUSxDQUFFLElBQVksRUFBRSxLQUFVO1FBQ3ZDLElBQUksQ0FBQyxZQUFZLENBQUMsSUFBSSxDQUFDLEdBQUcsT0FBTyxDQUFDLE9BQU8sQ0FBQyxLQUFLLENBQUMsQ0FBQztRQUNqRCxJQUFJLENBQUMsTUFBTSxDQUFDLElBQUksQ0FBQyxHQUFHLE1BQU0sS0FBSyxDQUFDO0lBQ2pDLENBQUM7O0FBR0YsTUFBTSxPQUFPLFVBQVU7SUFDZCxTQUFTLEdBQStCLEVBQUUsQ0FBQztJQUNuRCxXQUFXLEdBQXNCLEVBQUUsQ0FBQztJQUVwQyxlQUFlLENBQUUsT0FBZTtRQUMvQixJQUFJLENBQUMsT0FBTyxDQUFDLFVBQVUsQ0FBQyxPQUFPLENBQUMsRUFBRSxDQUFDO1lBQ2xDLE1BQU0sSUFBSSxLQUFLLENBQUMsaUJBQWlCLENBQUMsQ0FBQztRQUNwQyxDQUFDO1FBRUQsSUFBSSxTQUFTLEdBQUcsT0FBTyxDQUFDLE9BQU8sQ0FBQyxTQUFTLENBQUMsQ0FBQztRQUMzQyxJQUFJLFNBQVMsSUFBSSxDQUFDLENBQUMsRUFBRSxDQUFDO1lBQ3JCLFNBQVMsSUFBSSxTQUFTLENBQUMsTUFBTSxDQUFDO1lBQzlCLE9BQU8sSUFBSSxDQUFDLE9BQU8sQ0FBQyxNQUFNLENBQUMsU0FBUyxDQUFDLENBQUMsQ0FBQztRQUN4QyxDQUFDO2FBQU0sQ0FBQztZQUNQLE9BQU8sT0FBTyxDQUFDLE1BQU0sQ0FBQyxPQUFPLENBQUMsT0FBTyxDQUFDLEdBQUcsQ0FBQyxHQUFHLENBQUMsQ0FBQyxDQUFDO1FBQ2pELENBQUM7SUFDRixDQUFDO0lBRUQsa0JBQWtCLENBQUUsTUFBYztRQUNqQyxJQUFJLGFBQWEsR0FBRyxNQUFNLENBQUMsSUFBSSxDQUFDLE1BQU0sQ0FBQyxDQUFDO1FBQ3hDLElBQUksR0FBRyxHQUFHLGFBQWEsQ0FBQyxNQUFNLENBQUM7UUFDL0IsSUFBSSxLQUFLLEdBQUcsSUFBSSxVQUFVLENBQUMsR0FBRyxDQUFDLENBQUM7UUFDaEMsS0FBSyxJQUFJLENBQUMsR0FBRyxDQUFDLEVBQUUsQ0FBQyxHQUFHLEdBQUcsRUFBRSxDQUFDLEVBQUUsRUFBRSxDQUFDO1lBQzlCLEtBQUssQ0FBQyxDQUFDLENBQUMsR0FBRyxhQUFhLENBQUMsVUFBVSxDQUFDLENBQUMsQ0FBQyxDQUFDO1FBQ3hDLENBQUM7UUFDRCxPQUFPLEtBQUssQ0FBQztJQUNkLENBQUM7SUFFRCxtQkFBbUIsQ0FBRSxPQUFlO1FBQ25DLElBQUksQ0FBQyxPQUFPLENBQUMsVUFBVSxDQUFDLE9BQU8sQ0FBQyxFQUFFLENBQUM7WUFDbEMsTUFBTSxJQUFJLEtBQUssQ0FBQyxpQkFBaUIsQ0FBQyxDQUFDO1FBQ3BDLENBQUM7UUFFRCxJQUFJLFNBQVMsR0FBRyxPQUFPLENBQUMsT0FBTyxDQUFDLFNBQVMsQ0FBQyxDQUFDO1FBQzNDLElBQUksU0FBUyxJQUFJLENBQUMsQ0FBQztZQUFFLE1BQU0sSUFBSSxLQUFLLENBQUMsd0JBQXdCLENBQUMsQ0FBQztRQUMvRCxTQUFTLElBQUksU0FBUyxDQUFDLE1BQU0sQ0FBQztRQUM5QixPQUFPLElBQUksQ0FBQyxrQkFBa0IsQ0FBQyxPQUFPLENBQUMsTUFBTSxDQUFDLFNBQVMsQ0FBQyxDQUFDLENBQUM7SUFDM0QsQ0FBQztJQUVELFlBQVksQ0FBRSxHQUFXLEVBQUUsT0FBK0IsRUFBRSxLQUFxRDtRQUNoSCxJQUFJLElBQUksQ0FBQyxLQUFLLENBQUMsR0FBRyxFQUFFLE9BQU8sRUFBRSxLQUFLLENBQUM7WUFBRSxPQUFPO1FBRTVDLE1BQU0sVUFBVSxHQUFHLElBQUksQ0FBQyxXQUFXLENBQUMsR0FBRyxDQUFDLENBQUM7UUFDekMsdUZBQXVGO1FBQ3ZGLElBQUksVUFBVSxJQUFJLENBQUMsVUFBVSxDQUFDLFFBQVEsQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDO1lBQzdDLElBQUksQ0FBQztnQkFDSixJQUFJLENBQUMsTUFBTSxDQUFDLEdBQUcsRUFBRSxHQUFHLEVBQUUsSUFBSSxDQUFDLGVBQWUsQ0FBQyxVQUFVLENBQUMsQ0FBQyxDQUFDO1lBQ3pELENBQUM7WUFBQyxPQUFPLENBQUMsRUFBRSxDQUFDO2dCQUNaLElBQUksQ0FBQyxNQUFNLENBQUMsR0FBRyxFQUFFLEdBQUcsRUFBRSxJQUFJLENBQUMsU0FBUyxDQUFDLENBQUMsQ0FBQyxDQUFDLENBQUM7WUFDMUMsQ0FBQztZQUNELE9BQU87UUFDUixDQUFDO1FBRUQsSUFBSSxPQUFPLEdBQUcsSUFBSSxjQUFjLEVBQUUsQ0FBQztRQUNuQyxPQUFPLENBQUMsZ0JBQWdCLENBQUMsV0FBVyxDQUFDLENBQUM7UUFDdEMsT0FBTyxDQUFDLElBQUksQ0FBQyxLQUFLLEVBQUUsVUFBVSxDQUFDLENBQUMsQ0FBQyxVQUFVLENBQUMsQ0FBQyxDQUFDLEdBQUcsRUFBRSxJQUFJLENBQUMsQ0FBQztRQUN6RCxJQUFJLElBQUksR0FBRyxHQUFHLEVBQUU7WUFDZixJQUFJLENBQUMsTUFBTSxDQUFDLEdBQUcsRUFBRSxPQUFPLENBQUMsTUFBTSxFQUFFLE9BQU8sQ0FBQyxZQUFZLENBQUMsQ0FBQztRQUN4RCxDQUFDLENBQUM7UUFDRixPQUFPLENBQUMsTUFBTSxHQUFHLElBQUksQ0FBQztRQUN0QixPQUFPLENBQUMsT0FBTyxHQUFHLElBQUksQ0FBQztRQUN2QixPQUFPLENBQUMsSUFBSSxFQUFFLENBQUM7SUFDaEIsQ0FBQztJQUVELFlBQVksQ0FBRSxHQUFXLEVBQUUsT0FBK0IsRUFBRSxLQUFxRDtRQUNoSCxJQUFJLENBQUMsWUFBWSxDQUFDLEdBQUcsRUFBRSxDQUFDLElBQVksRUFBUSxFQUFFO1lBQzdDLE9BQU8sQ0FBQyxJQUFJLENBQUMsS0FBSyxDQUFDLElBQUksQ0FBQyxDQUFDLENBQUM7UUFDM0IsQ0FBQyxFQUFFLEtBQUssQ0FBQyxDQUFDO0lBQ1gsQ0FBQztJQUVELGNBQWMsQ0FBRSxHQUFXLEVBQUUsT0FBbUMsRUFBRSxLQUFxRDtRQUN0SCxJQUFJLElBQUksQ0FBQyxLQUFLLENBQUMsR0FBRyxFQUFFLE9BQU8sRUFBRSxLQUFLLENBQUM7WUFBRSxPQUFPO1FBRTVDLE1BQU0sVUFBVSxHQUFHLElBQUksQ0FBQyxXQUFXLENBQUMsR0FBRyxDQUFDLENBQUM7UUFDekMsdUZBQXVGO1FBQ3ZGLElBQUksVUFBVSxJQUFJLENBQUMsVUFBVSxDQUFDLFFBQVEsQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDO1lBQzdDLElBQUksQ0FBQztnQkFDSixJQUFJLENBQUMsTUFBTSxDQUFDLEdBQUcsRUFBRSxHQUFHLEVBQUUsSUFBSSxDQUFDLG1CQUFtQixDQUFDLFVBQVUsQ0FBQyxDQUFDLENBQUM7WUFDN0QsQ0FBQztZQUFDLE9BQU8sQ0FBQyxFQUFFLENBQUM7Z0JBQ1osSUFBSSxDQUFDLE1BQU0sQ0FBQyxHQUFHLEVBQUUsR0FBRyxFQUFFLElBQUksQ0FBQyxTQUFTLENBQUMsQ0FBQyxDQUFDLENBQUMsQ0FBQztZQUMxQyxDQUFDO1lBQ0QsT0FBTztRQUNSLENBQUM7UUFFRCxJQUFJLE9BQU8sR0FBRyxJQUFJLGNBQWMsRUFBRSxDQUFDO1FBQ25DLE9BQU8sQ0FBQyxJQUFJLENBQUMsS0FBSyxFQUFFLFVBQVUsQ0FBQyxDQUFDLENBQUMsVUFBVSxDQUFDLENBQUMsQ0FBQyxHQUFHLEVBQUUsSUFBSSxDQUFDLENBQUM7UUFDekQsT0FBTyxDQUFDLFlBQVksR0FBRyxhQUFhLENBQUM7UUFDckMsSUFBSSxPQUFPLEdBQUcsR0FBRyxFQUFFO1lBQ2xCLElBQUksQ0FBQyxNQUFNLENBQUMsR0FBRyxFQUFFLE9BQU8sQ0FBQyxNQUFNLEVBQUUsT0FBTyxDQUFDLFFBQVEsQ0FBQyxDQUFDO1FBQ3BELENBQUMsQ0FBQztRQUNGLE9BQU8sQ0FBQyxNQUFNLEdBQUcsR0FBRyxFQUFFO1lBQ3JCLElBQUksT0FBTyxDQUFDLE1BQU0sSUFBSSxHQUFHLElBQUksT0FBTyxDQUFDLE1BQU0sSUFBSSxDQUFDO2dCQUMvQyxJQUFJLENBQUMsTUFBTSxDQUFDLEdBQUcsRUFBRSxHQUFHLEVBQUUsSUFBSSxVQUFVLENBQUMsT0FBTyxDQUFDLFFBQXVCLENBQUMsQ0FBQyxDQUFDOztnQkFFdkUsT0FBTyxFQUFFLENBQUM7UUFDWixDQUFDLENBQUM7UUFDRixPQUFPLENBQUMsT0FBTyxHQUFHLE9BQU8sQ0FBQztRQUMxQixPQUFPLENBQUMsSUFBSSxFQUFFLENBQUM7SUFDaEIsQ0FBQztJQUVPLEtBQUssQ0FBRSxHQUFXLEVBQUUsT0FBWSxFQUFFLEtBQVU7UUFDbkQsSUFBSSxTQUFTLEdBQUcsSUFBSSxDQUFDLFNBQVMsQ0FBQyxHQUFHLENBQUMsQ0FBQztRQUNwQyxJQUFJLENBQUM7WUFDSixJQUFJLFNBQVM7Z0JBQUUsT0FBTyxJQUFJLENBQUM7WUFDM0IsSUFBSSxDQUFDLFNBQVMsQ0FBQyxHQUFHLENBQUMsR0FBRyxTQUFTLEdBQUcsRUFBRSxDQUFDO1FBQ3RDLENBQUM7Z0JBQVMsQ0FBQztZQUNWLFNBQVMsQ0FBQyxJQUFJLENBQUMsT0FBTyxFQUFFLEtBQUssQ0FBQyxDQUFDO1FBQ2hDLENBQUM7SUFDRixDQUFDO0lBRU8sTUFBTSxDQUFFLEdBQVcsRUFBRSxNQUFjLEVBQUUsSUFBUztRQUNyRCxJQUFJLFNBQVMsR0FBRyxJQUFJLENBQUMsU0FBUyxDQUFDLEdBQUcsQ0FBQyxDQUFDO1FBQ3BDLE9BQU8sSUFBSSxDQUFDLFNBQVMsQ0FBQyxHQUFHLENBQUMsQ0FBQztRQUMzQixJQUFJLElBQUksR0FBRyxNQUFNLElBQUksR0FBRyxJQUFJLE1BQU0sSUFBSSxDQUFDLENBQUMsQ0FBQyxDQUFDLENBQUMsSUFBSSxDQUFDLENBQUMsQ0FBQyxDQUFDLENBQUMsTUFBTSxFQUFFLElBQUksQ0FBQyxDQUFDO1FBQ2xFLEtBQUssSUFBSSxDQUFDLEdBQUcsSUFBSSxDQUFDLE1BQU0sR0FBRyxDQUFDLEVBQUUsQ0FBQyxHQUFHLFNBQVMsQ0FBQyxNQUFNLEVBQUUsQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLElBQUksQ0FBQztZQUNoRSxTQUFTLENBQUMsQ0FBQyxDQUFDLENBQUMsS0FBSyxDQUFDLElBQUksRUFBRSxJQUFJLENBQUMsQ0FBQztJQUNqQyxDQUFDO0NBQ0QiLCJzb3VyY2VzQ29udGVudCI6WyIvKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqXG4gKiBTcGluZSBSdW50aW1lcyBMaWNlbnNlIEFncmVlbWVudFxuICogTGFzdCB1cGRhdGVkIEFwcmlsIDUsIDIwMjUuIFJlcGxhY2VzIGFsbCBwcmlvciB2ZXJzaW9ucy5cbiAqXG4gKiBDb3B5cmlnaHQgKGMpIDIwMTMtMjAyNSwgRXNvdGVyaWMgU29mdHdhcmUgTExDXG4gKlxuICogSW50ZWdyYXRpb24gb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmUgb3Igb3RoZXJ3aXNlIGNyZWF0aW5nXG4gKiBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpcyBwZXJtaXR0ZWQgdW5kZXIgdGhlIHRlcm1zIGFuZFxuICogY29uZGl0aW9ucyBvZiBTZWN0aW9uIDIgb2YgdGhlIFNwaW5lIEVkaXRvciBMaWNlbnNlIEFncmVlbWVudDpcbiAqIGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1lZGl0b3ItbGljZW5zZVxuICpcbiAqIE90aGVyd2lzZSwgaXQgaXMgcGVybWl0dGVkIHRvIGludGVncmF0ZSB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZVxuICogb3Igb3RoZXJ3aXNlIGNyZWF0ZSBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyAoY29sbGVjdGl2ZWx5LFxuICogXCJQcm9kdWN0c1wiKSwgcHJvdmlkZWQgdGhhdCBlYWNoIHVzZXIgb2YgdGhlIFByb2R1Y3RzIG11c3Qgb2J0YWluIHRoZWlyIG93blxuICogU3BpbmUgRWRpdG9yIGxpY2Vuc2UgYW5kIHJlZGlzdHJpYnV0aW9uIG9mIHRoZSBQcm9kdWN0cyBpbiBhbnkgZm9ybSBtdXN0XG4gKiBpbmNsdWRlIHRoaXMgbGljZW5zZSBhbmQgY29weXJpZ2h0IG5vdGljZS5cbiAqXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMgQVJFIFBST1ZJREVEIEJZIEVTT1RFUklDIFNPRlRXQVJFIExMQyBcIkFTIElTXCIgQU5EIEFOWVxuICogRVhQUkVTUyBPUiBJTVBMSUVEIFdBUlJBTlRJRVMsIElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBUSEUgSU1QTElFRFxuICogV0FSUkFOVElFUyBPRiBNRVJDSEFOVEFCSUxJVFkgQU5EIEZJVE5FU1MgRk9SIEEgUEFSVElDVUxBUiBQVVJQT1NFIEFSRVxuICogRElTQ0xBSU1FRC4gSU4gTk8gRVZFTlQgU0hBTEwgRVNPVEVSSUMgU09GVFdBUkUgTExDIEJFIExJQUJMRSBGT1IgQU5ZXG4gKiBESVJFQ1QsIElORElSRUNULCBJTkNJREVOVEFMLCBTUEVDSUFMLCBFWEVNUExBUlksIE9SIENPTlNFUVVFTlRJQUwgREFNQUdFU1xuICogKElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBQUk9DVVJFTUVOVCBPRiBTVUJTVElUVVRFIEdPT0RTIE9SIFNFUlZJQ0VTLFxuICogQlVTSU5FU1MgSU5URVJSVVBUSU9OLCBPUiBMT1NTIE9GIFVTRSwgREFUQSwgT1IgUFJPRklUUykgSE9XRVZFUiBDQVVTRUQgQU5EXG4gKiBPTiBBTlkgVEhFT1JZIE9GIExJQUJJTElUWSwgV0hFVEhFUiBJTiBDT05UUkFDVCwgU1RSSUNUIExJQUJJTElUWSwgT1IgVE9SVFxuICogKElOQ0xVRElORyBORUdMSUdFTkNFIE9SIE9USEVSV0lTRSkgQVJJU0lORyBJTiBBTlkgV0FZIE9VVCBPRiBUSEUgVVNFIE9GXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMsIEVWRU4gSUYgQURWSVNFRCBPRiBUSEUgUE9TU0lCSUxJVFkgT0YgU1VDSCBEQU1BR0UuXG4gKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKiovXG5cbmltcG9ydCB7IFRleHR1cmUgfSBmcm9tIFwiLi9UZXh0dXJlLmpzXCI7XG5pbXBvcnQgeyBUZXh0dXJlQXRsYXMgfSBmcm9tIFwiLi9UZXh0dXJlQXRsYXMuanNcIjtcbmltcG9ydCB7IERpc3Bvc2FibGUsIFN0cmluZ01hcCB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5cbmV4cG9ydCBjbGFzcyBBc3NldE1hbmFnZXJCYXNlIGltcGxlbWVudHMgRGlzcG9zYWJsZSB7XG5cdHByaXZhdGUgcGF0aFByZWZpeDogc3RyaW5nID0gXCJcIjtcblx0cHJpdmF0ZSB0ZXh0dXJlTG9hZGVyOiAoaW1hZ2U6IEhUTUxJbWFnZUVsZW1lbnQgfCBJbWFnZUJpdG1hcCkgPT4gVGV4dHVyZTtcblx0cHJpdmF0ZSBkb3dubG9hZGVyOiBEb3dubG9hZGVyO1xuXHRwcml2YXRlIGNhY2hlOiBBc3NldENhY2hlO1xuXHRwcml2YXRlIGVycm9yczogU3RyaW5nTWFwPHN0cmluZz4gPSB7fTtcblx0cHJpdmF0ZSB0b0xvYWQgPSAwO1xuXHRwcml2YXRlIGxvYWRlZCA9IDA7XG5cblx0Y29uc3RydWN0b3IgKHRleHR1cmVMb2FkZXI6IChpbWFnZTogSFRNTEltYWdlRWxlbWVudCB8IEltYWdlQml0bWFwKSA9PiBUZXh0dXJlLCBwYXRoUHJlZml4OiBzdHJpbmcgPSBcIlwiLCBkb3dubG9hZGVyID0gbmV3IERvd25sb2FkZXIoKSwgY2FjaGUgPSBuZXcgQXNzZXRDYWNoZSgpKSB7XG5cdFx0dGhpcy50ZXh0dXJlTG9hZGVyID0gdGV4dHVyZUxvYWRlcjtcblx0XHR0aGlzLnBhdGhQcmVmaXggPSBwYXRoUHJlZml4O1xuXHRcdHRoaXMuZG93bmxvYWRlciA9IGRvd25sb2FkZXI7XG5cdFx0dGhpcy5jYWNoZSA9IGNhY2hlO1xuXHR9XG5cblx0cHJpdmF0ZSBzdGFydCAocGF0aDogc3RyaW5nKTogc3RyaW5nIHtcblx0XHR0aGlzLnRvTG9hZCsrO1xuXHRcdHJldHVybiB0aGlzLnBhdGhQcmVmaXggKyBwYXRoO1xuXHR9XG5cblx0cHJpdmF0ZSBzdWNjZXNzIChjYWxsYmFjazogKHBhdGg6IHN0cmluZywgZGF0YTogYW55KSA9PiB2b2lkLCBwYXRoOiBzdHJpbmcsIGFzc2V0OiBhbnkpIHtcblx0XHR0aGlzLnRvTG9hZC0tO1xuXHRcdHRoaXMubG9hZGVkKys7XG5cdFx0dGhpcy5jYWNoZS5hc3NldHNbcGF0aF0gPSBhc3NldDtcblx0XHR0aGlzLmNhY2hlLmFzc2V0c1JlZkNvdW50W3BhdGhdID0gKHRoaXMuY2FjaGUuYXNzZXRzUmVmQ291bnRbcGF0aF0gfHwgMCkgKyAxO1xuXHRcdGlmIChjYWxsYmFjaykgY2FsbGJhY2socGF0aCwgYXNzZXQpO1xuXHR9XG5cblx0cHJpdmF0ZSBlcnJvciAoY2FsbGJhY2s6IChwYXRoOiBzdHJpbmcsIG1lc3NhZ2U6IHN0cmluZykgPT4gdm9pZCwgcGF0aDogc3RyaW5nLCBtZXNzYWdlOiBzdHJpbmcpIHtcblx0XHR0aGlzLnRvTG9hZC0tO1xuXHRcdHRoaXMubG9hZGVkKys7XG5cdFx0dGhpcy5lcnJvcnNbcGF0aF0gPSBtZXNzYWdlO1xuXHRcdGlmIChjYWxsYmFjaykgY2FsbGJhY2socGF0aCwgbWVzc2FnZSk7XG5cdH1cblxuXHRsb2FkQWxsICgpIHtcblx0XHRsZXQgcHJvbWlzZSA9IG5ldyBQcm9taXNlKChyZXNvbHZlOiAoYXNzZXRNYW5hZ2VyOiBBc3NldE1hbmFnZXJCYXNlKSA9PiB2b2lkLCByZWplY3Q6IChlcnJvcnM6IFN0cmluZ01hcDxzdHJpbmc+KSA9PiB2b2lkKSA9PiB7XG5cdFx0XHRsZXQgY2hlY2sgPSAoKSA9PiB7XG5cdFx0XHRcdGlmICh0aGlzLmlzTG9hZGluZ0NvbXBsZXRlKCkpIHtcblx0XHRcdFx0XHRpZiAodGhpcy5oYXNFcnJvcnMoKSkgcmVqZWN0KHRoaXMuZXJyb3JzKTtcblx0XHRcdFx0XHRlbHNlIHJlc29sdmUodGhpcyk7XG5cdFx0XHRcdFx0cmV0dXJuO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHJlcXVlc3RBbmltYXRpb25GcmFtZShjaGVjayk7XG5cdFx0XHR9XG5cdFx0XHRyZXF1ZXN0QW5pbWF0aW9uRnJhbWUoY2hlY2spO1xuXHRcdH0pO1xuXHRcdHJldHVybiBwcm9taXNlO1xuXHR9XG5cblx0c2V0UmF3RGF0YVVSSSAocGF0aDogc3RyaW5nLCBkYXRhOiBzdHJpbmcpIHtcblx0XHR0aGlzLmRvd25sb2FkZXIucmF3RGF0YVVyaXNbdGhpcy5wYXRoUHJlZml4ICsgcGF0aF0gPSBkYXRhO1xuXHR9XG5cblx0bG9hZEJpbmFyeSAocGF0aDogc3RyaW5nLFxuXHRcdHN1Y2Nlc3M6IChwYXRoOiBzdHJpbmcsIGJpbmFyeTogVWludDhBcnJheSkgPT4gdm9pZCA9ICgpID0+IHsgfSxcblx0XHRlcnJvcjogKHBhdGg6IHN0cmluZywgbWVzc2FnZTogc3RyaW5nKSA9PiB2b2lkID0gKCkgPT4geyB9KSB7XG5cdFx0cGF0aCA9IHRoaXMuc3RhcnQocGF0aCk7XG5cblx0XHRpZiAodGhpcy5yZXVzZUFzc2V0cyhwYXRoLCBzdWNjZXNzLCBlcnJvcikpIHJldHVybjtcblxuXHRcdHRoaXMuY2FjaGUuYXNzZXRzTG9hZGVkW3BhdGhdID0gbmV3IFByb21pc2U8YW55PigocmVzb2x2ZSwgcmVqZWN0KSA9PiB7XG5cdFx0XHR0aGlzLmRvd25sb2FkZXIuZG93bmxvYWRCaW5hcnkocGF0aCwgKGRhdGE6IFVpbnQ4QXJyYXkpOiB2b2lkID0+IHtcblx0XHRcdFx0dGhpcy5zdWNjZXNzKHN1Y2Nlc3MsIHBhdGgsIGRhdGEpO1xuXHRcdFx0XHRyZXNvbHZlKGRhdGEpO1xuXHRcdFx0fSwgKHN0YXR1czogbnVtYmVyLCByZXNwb25zZVRleHQ6IHN0cmluZyk6IHZvaWQgPT4ge1xuXHRcdFx0XHRjb25zdCBlcnJvck1zZyA9IGBDb3VsZG4ndCBsb2FkIGJpbmFyeSAke3BhdGh9OiBzdGF0dXMgJHtzdGF0dXN9LCAke3Jlc3BvbnNlVGV4dH1gO1xuXHRcdFx0XHR0aGlzLmVycm9yKGVycm9yLCBwYXRoLCBlcnJvck1zZyk7XG5cdFx0XHRcdHJlamVjdChlcnJvck1zZyk7XG5cdFx0XHR9KTtcblx0XHR9KTtcblx0fVxuXG5cdGxvYWRUZXh0IChwYXRoOiBzdHJpbmcsXG5cdFx0c3VjY2VzczogKHBhdGg6IHN0cmluZywgdGV4dDogc3RyaW5nKSA9PiB2b2lkID0gKCkgPT4geyB9LFxuXHRcdGVycm9yOiAocGF0aDogc3RyaW5nLCBtZXNzYWdlOiBzdHJpbmcpID0+IHZvaWQgPSAoKSA9PiB7IH0pIHtcblx0XHRwYXRoID0gdGhpcy5zdGFydChwYXRoKTtcblxuXHRcdHRoaXMuZG93bmxvYWRlci5kb3dubG9hZFRleHQocGF0aCwgKGRhdGE6IHN0cmluZyk6IHZvaWQgPT4ge1xuXHRcdFx0dGhpcy5zdWNjZXNzKHN1Y2Nlc3MsIHBhdGgsIGRhdGEpO1xuXHRcdH0sIChzdGF0dXM6IG51bWJlciwgcmVzcG9uc2VUZXh0OiBzdHJpbmcpOiB2b2lkID0+IHtcblx0XHRcdHRoaXMuZXJyb3IoZXJyb3IsIHBhdGgsIGBDb3VsZG4ndCBsb2FkIHRleHQgJHtwYXRofTogc3RhdHVzICR7c3RhdHVzfSwgJHtyZXNwb25zZVRleHR9YCk7XG5cdFx0fSk7XG5cdH1cblxuXHRsb2FkSnNvbiAocGF0aDogc3RyaW5nLFxuXHRcdHN1Y2Nlc3M6IChwYXRoOiBzdHJpbmcsIG9iamVjdDogb2JqZWN0KSA9PiB2b2lkID0gKCkgPT4geyB9LFxuXHRcdGVycm9yOiAocGF0aDogc3RyaW5nLCBtZXNzYWdlOiBzdHJpbmcpID0+IHZvaWQgPSAoKSA9PiB7IH0pIHtcblx0XHRwYXRoID0gdGhpcy5zdGFydChwYXRoKTtcblxuXHRcdGlmICh0aGlzLnJldXNlQXNzZXRzKHBhdGgsIHN1Y2Nlc3MsIGVycm9yKSkgcmV0dXJuO1xuXG5cdFx0dGhpcy5jYWNoZS5hc3NldHNMb2FkZWRbcGF0aF0gPSBuZXcgUHJvbWlzZTxhbnk+KChyZXNvbHZlLCByZWplY3QpID0+IHtcblx0XHRcdHRoaXMuZG93bmxvYWRlci5kb3dubG9hZEpzb24ocGF0aCwgKGRhdGE6IG9iamVjdCk6IHZvaWQgPT4ge1xuXHRcdFx0XHR0aGlzLnN1Y2Nlc3Moc3VjY2VzcywgcGF0aCwgZGF0YSk7XG5cdFx0XHRcdHJlc29sdmUoZGF0YSk7XG5cdFx0XHR9LCAoc3RhdHVzOiBudW1iZXIsIHJlc3BvbnNlVGV4dDogc3RyaW5nKTogdm9pZCA9PiB7XG5cdFx0XHRcdGNvbnN0IGVycm9yTXNnID0gYENvdWxkbid0IGxvYWQgSlNPTiAke3BhdGh9OiBzdGF0dXMgJHtzdGF0dXN9LCAke3Jlc3BvbnNlVGV4dH1gO1xuXHRcdFx0XHR0aGlzLmVycm9yKGVycm9yLCBwYXRoLCBlcnJvck1zZyk7XG5cdFx0XHRcdHJlamVjdChlcnJvck1zZyk7XG5cdFx0XHR9KTtcblx0XHR9KTtcblx0fVxuXG5cdHJldXNlQXNzZXRzIChwYXRoOiBzdHJpbmcsXG5cdFx0c3VjY2VzczogKHBhdGg6IHN0cmluZywgZGF0YTogYW55KSA9PiB2b2lkID0gKCkgPT4geyB9LFxuXHRcdGVycm9yOiAocGF0aDogc3RyaW5nLCBtZXNzYWdlOiBzdHJpbmcpID0+IHZvaWQgPSAoKSA9PiB7IH0pIHtcblx0XHRjb25zdCBsb2FkZWRTdGF0dXMgPSB0aGlzLmNhY2hlLmFzc2V0c0xvYWRlZFtwYXRoXTtcblx0XHRjb25zdCBhbHJlYWR5RXhpc3RzT3JMb2FkaW5nID0gbG9hZGVkU3RhdHVzICE9PSB1bmRlZmluZWQ7XG5cdFx0aWYgKGFscmVhZHlFeGlzdHNPckxvYWRpbmcpIHtcblx0XHRcdHRoaXMuY2FjaGUuYXNzZXRzTG9hZGVkW3BhdGhdID0gbG9hZGVkU3RhdHVzXG5cdFx0XHRcdC50aGVuKGRhdGEgPT4ge1xuXHRcdFx0XHRcdC8vIG5lY2Vzc2FyeSB3aGVuIHVzZXIgcHJlbG9hZHMgYW4gaW1hZ2UgaW50byB0aGUgY2FjaGUuXG5cdFx0XHRcdFx0Ly8gdGV4dHVyZSBsb2FkZXIgaXMgbm90IGF2YWlhYmxlIGluIHRoZSBjYWNoZSwgc28gd2UgdHJhbnNmb3JtIGluIEdMVGV4dHVyZSBhdCBmaXJzdCB1c2Vcblx0XHRcdFx0XHRkYXRhID0gKGRhdGEgaW5zdGFuY2VvZiBJbWFnZSB8fCBkYXRhIGluc3RhbmNlb2YgSW1hZ2VCaXRtYXApID8gdGhpcy50ZXh0dXJlTG9hZGVyKGRhdGEpIDogZGF0YTtcblx0XHRcdFx0XHR0aGlzLnN1Y2Nlc3Moc3VjY2VzcywgcGF0aCwgZGF0YSk7XG5cdFx0XHRcdFx0cmV0dXJuIGRhdGE7XG5cdFx0XHRcdH0pXG5cdFx0XHRcdC5jYXRjaChlcnJvck1zZyA9PiB0aGlzLmVycm9yKGVycm9yLCBwYXRoLCBlcnJvck1zZykpO1xuXHRcdH1cblx0XHRyZXR1cm4gYWxyZWFkeUV4aXN0c09yTG9hZGluZztcblx0fVxuXG5cdGxvYWRUZXh0dXJlIChwYXRoOiBzdHJpbmcsXG5cdFx0c3VjY2VzczogKHBhdGg6IHN0cmluZywgdGV4dHVyZTogVGV4dHVyZSkgPT4gdm9pZCA9ICgpID0+IHsgfSxcblx0XHRlcnJvcjogKHBhdGg6IHN0cmluZywgbWVzc2FnZTogc3RyaW5nKSA9PiB2b2lkID0gKCkgPT4geyB9KSB7XG5cblx0XHRwYXRoID0gdGhpcy5zdGFydChwYXRoKTtcblxuXHRcdGlmICh0aGlzLnJldXNlQXNzZXRzKHBhdGgsIHN1Y2Nlc3MsIGVycm9yKSkgcmV0dXJuO1xuXG5cdFx0dGhpcy5jYWNoZS5hc3NldHNMb2FkZWRbcGF0aF0gPSBuZXcgUHJvbWlzZTxhbnk+KChyZXNvbHZlLCByZWplY3QpID0+IHtcblx0XHRcdGxldCBpc0Jyb3dzZXIgPSAhISh0eXBlb2Ygd2luZG93ICE9PSAndW5kZWZpbmVkJyAmJiB0eXBlb2YgbmF2aWdhdG9yICE9PSAndW5kZWZpbmVkJyAmJiB3aW5kb3cuZG9jdW1lbnQpO1xuXHRcdFx0bGV0IGlzV2ViV29ya2VyID0gIWlzQnJvd3NlcjsgLy8gJiYgdHlwZW9mIGltcG9ydFNjcmlwdHMgIT09ICd1bmRlZmluZWQnO1xuXHRcdFx0aWYgKGlzV2ViV29ya2VyKSB7XG5cdFx0XHRcdGZldGNoKHBhdGgsIHsgbW9kZTogPFJlcXVlc3RNb2RlPlwiY29yc1wiIH0pLnRoZW4oKHJlc3BvbnNlKSA9PiB7XG5cdFx0XHRcdFx0aWYgKHJlc3BvbnNlLm9rKSByZXR1cm4gcmVzcG9uc2UuYmxvYigpO1xuXHRcdFx0XHRcdGNvbnN0IGVycm9yTXNnID0gYENvdWxkbid0IGxvYWQgaW1hZ2U6ICR7cGF0aH1gO1xuXHRcdFx0XHRcdHRoaXMuZXJyb3IoZXJyb3IsIHBhdGgsIGBDb3VsZG4ndCBsb2FkIGltYWdlOiAke3BhdGh9YCk7XG5cdFx0XHRcdFx0cmVqZWN0KGVycm9yTXNnKTtcblx0XHRcdFx0fSkudGhlbigoYmxvYikgPT4ge1xuXHRcdFx0XHRcdHJldHVybiBibG9iID8gY3JlYXRlSW1hZ2VCaXRtYXAoYmxvYiwgeyBwcmVtdWx0aXBseUFscGhhOiBcIm5vbmVcIiwgY29sb3JTcGFjZUNvbnZlcnNpb246IFwibm9uZVwiIH0pIDogbnVsbDtcblx0XHRcdFx0fSkudGhlbigoYml0bWFwKSA9PiB7XG5cdFx0XHRcdFx0aWYgKGJpdG1hcCkge1xuXHRcdFx0XHRcdFx0Y29uc3QgdGV4dHVyZSA9IHRoaXMuY3JlYXRlVGV4dHVyZShwYXRoLCBiaXRtYXApO1xuXHRcdFx0XHRcdFx0dGhpcy5zdWNjZXNzKHN1Y2Nlc3MsIHBhdGgsIHRleHR1cmUpO1xuXHRcdFx0XHRcdFx0cmVzb2x2ZSh0ZXh0dXJlKTtcblx0XHRcdFx0XHR9O1xuXHRcdFx0XHR9KTtcblx0XHRcdH0gZWxzZSB7XG5cdFx0XHRcdGxldCBpbWFnZSA9IG5ldyBJbWFnZSgpO1xuXHRcdFx0XHRpbWFnZS5jcm9zc09yaWdpbiA9IFwiYW5vbnltb3VzXCI7XG5cdFx0XHRcdGltYWdlLm9ubG9hZCA9ICgpID0+IHtcblx0XHRcdFx0XHRjb25zdCB0ZXh0dXJlID0gdGhpcy5jcmVhdGVUZXh0dXJlKHBhdGgsIGltYWdlKTtcblx0XHRcdFx0XHR0aGlzLnN1Y2Nlc3Moc3VjY2VzcywgcGF0aCwgdGV4dHVyZSk7XG5cdFx0XHRcdFx0cmVzb2x2ZSh0ZXh0dXJlKTtcblx0XHRcdFx0fTtcblx0XHRcdFx0aW1hZ2Uub25lcnJvciA9ICgpID0+IHtcblx0XHRcdFx0XHRjb25zdCBlcnJvck1zZyA9IGBDb3VsZG4ndCBsb2FkIGltYWdlOiAke3BhdGh9YDtcblx0XHRcdFx0XHR0aGlzLmVycm9yKGVycm9yLCBwYXRoLCBlcnJvck1zZyk7XG5cdFx0XHRcdFx0cmVqZWN0KGVycm9yTXNnKTtcblx0XHRcdFx0fTtcblx0XHRcdFx0aWYgKHRoaXMuZG93bmxvYWRlci5yYXdEYXRhVXJpc1twYXRoXSkgcGF0aCA9IHRoaXMuZG93bmxvYWRlci5yYXdEYXRhVXJpc1twYXRoXTtcblx0XHRcdFx0aW1hZ2Uuc3JjID0gcGF0aDtcblx0XHRcdH1cblx0XHR9KTtcblx0fVxuXG5cdGxvYWRUZXh0dXJlQXRsYXMgKHBhdGg6IHN0cmluZyxcblx0XHRzdWNjZXNzOiAocGF0aDogc3RyaW5nLCBhdGxhczogVGV4dHVyZUF0bGFzKSA9PiB2b2lkID0gKCkgPT4geyB9LFxuXHRcdGVycm9yOiAocGF0aDogc3RyaW5nLCBtZXNzYWdlOiBzdHJpbmcpID0+IHZvaWQgPSAoKSA9PiB7IH0sXG5cdFx0ZmlsZUFsaWFzPzogeyBba2V5d29yZDogc3RyaW5nXTogc3RyaW5nIH1cblx0KSB7XG5cdFx0bGV0IGluZGV4ID0gcGF0aC5sYXN0SW5kZXhPZihcIi9cIik7XG5cdFx0bGV0IHBhcmVudCA9IGluZGV4ID49IDAgPyBwYXRoLnN1YnN0cmluZygwLCBpbmRleCArIDEpIDogXCJcIjtcblx0XHRwYXRoID0gdGhpcy5zdGFydChwYXRoKTtcblxuXHRcdGlmICh0aGlzLnJldXNlQXNzZXRzKHBhdGgsIHN1Y2Nlc3MsIGVycm9yKSkgcmV0dXJuO1xuXG5cdFx0dGhpcy5jYWNoZS5hc3NldHNMb2FkZWRbcGF0aF0gPSBuZXcgUHJvbWlzZTxhbnk+KChyZXNvbHZlLCByZWplY3QpID0+IHtcblx0XHRcdHRoaXMuZG93bmxvYWRlci5kb3dubG9hZFRleHQocGF0aCwgKGF0bGFzVGV4dDogc3RyaW5nKTogdm9pZCA9PiB7XG5cdFx0XHRcdHRyeSB7XG5cdFx0XHRcdFx0Y29uc3QgYXRsYXMgPSB0aGlzLmNyZWF0ZVRleHR1cmVBdGxhcyhwYXRoLCBhdGxhc1RleHQpO1xuXHRcdFx0XHRcdGxldCB0b0xvYWQgPSBhdGxhcy5wYWdlcy5sZW5ndGgsIGFib3J0ID0gZmFsc2U7XG5cblx0XHRcdFx0XHRpZiAodG9Mb2FkID09PSAwKSB7XG5cdFx0XHRcdFx0XHR0aGlzLnN1Y2Nlc3Moc3VjY2VzcywgcGF0aCwgYXRsYXMpO1xuXHRcdFx0XHRcdFx0cmVzb2x2ZShhdGxhcyk7XG5cdFx0XHRcdFx0XHRyZXR1cm47XG5cdFx0XHRcdFx0fVxuXG5cdFx0XHRcdFx0Zm9yIChsZXQgcGFnZSBvZiBhdGxhcy5wYWdlcykge1xuXHRcdFx0XHRcdFx0dGhpcy5sb2FkVGV4dHVyZSghZmlsZUFsaWFzID8gcGFyZW50ICsgcGFnZS5uYW1lIDogZmlsZUFsaWFzW3BhZ2UubmFtZSFdLFxuXHRcdFx0XHRcdFx0XHQoaW1hZ2VQYXRoOiBzdHJpbmcsIHRleHR1cmU6IFRleHR1cmUpID0+IHtcblx0XHRcdFx0XHRcdFx0XHRpZiAoIWFib3J0KSB7XG5cdFx0XHRcdFx0XHRcdFx0XHRwYWdlLnNldFRleHR1cmUodGV4dHVyZSk7XG5cdFx0XHRcdFx0XHRcdFx0XHRpZiAoLS10b0xvYWQgPT0gMCkge1xuXHRcdFx0XHRcdFx0XHRcdFx0XHR0aGlzLnN1Y2Nlc3Moc3VjY2VzcywgcGF0aCwgYXRsYXMpO1xuXHRcdFx0XHRcdFx0XHRcdFx0XHRyZXNvbHZlKGF0bGFzKTtcblx0XHRcdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdH0sXG5cdFx0XHRcdFx0XHRcdChpbWFnZVBhdGg6IHN0cmluZywgbWVzc2FnZTogc3RyaW5nKSA9PiB7XG5cdFx0XHRcdFx0XHRcdFx0aWYgKCFhYm9ydCkge1xuXHRcdFx0XHRcdFx0XHRcdFx0Y29uc3QgZXJyb3JNc2cgPSBgQ291bGRuJ3QgbG9hZCB0ZXh0dXJlICR7cGF0aH0gcGFnZSBpbWFnZTogJHtpbWFnZVBhdGh9YDtcblx0XHRcdFx0XHRcdFx0XHRcdHRoaXMuZXJyb3IoZXJyb3IsIHBhdGgsIGVycm9yTXNnKTtcblx0XHRcdFx0XHRcdFx0XHRcdHJlamVjdChlcnJvck1zZyk7XG5cdFx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHRcdGFib3J0ID0gdHJ1ZTtcblx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0KTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdH0gY2F0Y2ggKGUpIHtcblx0XHRcdFx0XHRjb25zdCBlcnJvck1zZyA9IGBDb3VsZG4ndCBwYXJzZSB0ZXh0dXJlIGF0bGFzICR7cGF0aH06ICR7KGUgYXMgYW55KS5tZXNzYWdlfWA7XG5cdFx0XHRcdFx0dGhpcy5lcnJvcihlcnJvciwgcGF0aCwgZXJyb3JNc2cpO1xuXHRcdFx0XHRcdHJlamVjdChlcnJvck1zZyk7XG5cdFx0XHRcdH1cblx0XHRcdH0sIChzdGF0dXM6IG51bWJlciwgcmVzcG9uc2VUZXh0OiBzdHJpbmcpOiB2b2lkID0+IHtcblx0XHRcdFx0Y29uc3QgZXJyb3JNc2cgPSBgQ291bGRuJ3QgbG9hZCB0ZXh0dXJlIGF0bGFzICR7cGF0aH06IHN0YXR1cyAke3N0YXR1c30sICR7cmVzcG9uc2VUZXh0fWA7XG5cdFx0XHRcdHRoaXMuZXJyb3IoZXJyb3IsIHBhdGgsIGVycm9yTXNnKTtcblx0XHRcdFx0cmVqZWN0KGVycm9yTXNnKTtcblx0XHRcdH0pO1xuXHRcdH0pO1xuXHR9XG5cblx0bG9hZFRleHR1cmVBdGxhc0J1dE5vVGV4dHVyZXMgKHBhdGg6IHN0cmluZyxcblx0XHRzdWNjZXNzOiAocGF0aDogc3RyaW5nLCBhdGxhczogVGV4dHVyZUF0bGFzKSA9PiB2b2lkID0gKCkgPT4geyB9LFxuXHRcdGVycm9yOiAocGF0aDogc3RyaW5nLCBtZXNzYWdlOiBzdHJpbmcpID0+IHZvaWQgPSAoKSA9PiB7IH0sXG5cdFx0ZmlsZUFsaWFzPzogeyBba2V5d29yZDogc3RyaW5nXTogc3RyaW5nIH1cblx0KSB7XG5cdFx0cGF0aCA9IHRoaXMuc3RhcnQocGF0aCk7XG5cblx0XHRpZiAodGhpcy5yZXVzZUFzc2V0cyhwYXRoLCBzdWNjZXNzLCBlcnJvcikpIHJldHVybjtcblxuXHRcdHRoaXMuY2FjaGUuYXNzZXRzTG9hZGVkW3BhdGhdID0gbmV3IFByb21pc2U8YW55PigocmVzb2x2ZSwgcmVqZWN0KSA9PiB7XG5cdFx0XHR0aGlzLmRvd25sb2FkZXIuZG93bmxvYWRUZXh0KHBhdGgsIChhdGxhc1RleHQ6IHN0cmluZyk6IHZvaWQgPT4ge1xuXHRcdFx0XHR0cnkge1xuXHRcdFx0XHRcdGNvbnN0IGF0bGFzID0gdGhpcy5jcmVhdGVUZXh0dXJlQXRsYXMocGF0aCwgYXRsYXNUZXh0KTtcblx0XHRcdFx0XHR0aGlzLnN1Y2Nlc3Moc3VjY2VzcywgcGF0aCwgYXRsYXMpO1xuXHRcdFx0XHRcdHJlc29sdmUoYXRsYXMpO1xuXHRcdFx0XHR9IGNhdGNoIChlKSB7XG5cdFx0XHRcdFx0Y29uc3QgZXJyb3JNc2cgPSBgQ291bGRuJ3QgcGFyc2UgdGV4dHVyZSBhdGxhcyAke3BhdGh9OiAkeyhlIGFzIGFueSkubWVzc2FnZX1gO1xuXHRcdFx0XHRcdHRoaXMuZXJyb3IoZXJyb3IsIHBhdGgsIGVycm9yTXNnKTtcblx0XHRcdFx0XHRyZWplY3QoZXJyb3JNc2cpO1xuXHRcdFx0XHR9XG5cdFx0XHR9LCAoc3RhdHVzOiBudW1iZXIsIHJlc3BvbnNlVGV4dDogc3RyaW5nKTogdm9pZCA9PiB7XG5cdFx0XHRcdGNvbnN0IGVycm9yTXNnID0gYENvdWxkbid0IGxvYWQgdGV4dHVyZSBhdGxhcyAke3BhdGh9OiBzdGF0dXMgJHtzdGF0dXN9LCAke3Jlc3BvbnNlVGV4dH1gO1xuXHRcdFx0XHR0aGlzLmVycm9yKGVycm9yLCBwYXRoLCBlcnJvck1zZyk7XG5cdFx0XHRcdHJlamVjdChlcnJvck1zZyk7XG5cdFx0XHR9KTtcblx0XHR9KTtcblx0fVxuXG5cdC8vIFByb21pc2lmaWVkIHZlcnNpb25zIG9mIGxvYWQgZnVuY3Rpb25cblx0YXN5bmMgbG9hZEJpbmFyeUFzeW5jIChwYXRoOiBzdHJpbmcpIHtcblx0XHRyZXR1cm4gbmV3IFByb21pc2UoKHJlc29sdmUsIHJlamVjdCkgPT4ge1xuXHRcdFx0dGhpcy5sb2FkQmluYXJ5KHBhdGgsXG5cdFx0XHRcdChfLCBiaW5hcnkpID0+IHJlc29sdmUoYmluYXJ5KSxcblx0XHRcdFx0KF8sIG1lc3NhZ2UpID0+IHJlamVjdChtZXNzYWdlKSxcblx0XHRcdCk7XG5cdFx0fSk7XG5cdH1cblxuXHRhc3luYyBsb2FkSnNvbkFzeW5jIChwYXRoOiBzdHJpbmcpIHtcblx0XHRyZXR1cm4gbmV3IFByb21pc2UoKHJlc29sdmUsIHJlamVjdCkgPT4ge1xuXHRcdFx0dGhpcy5sb2FkSnNvbihwYXRoLFxuXHRcdFx0XHQoXywgb2JqZWN0KSA9PiByZXNvbHZlKG9iamVjdCksXG5cdFx0XHRcdChfLCBtZXNzYWdlKSA9PiByZWplY3QobWVzc2FnZSksXG5cdFx0XHQpO1xuXHRcdH0pO1xuXHR9XG5cblx0YXN5bmMgbG9hZFRleHR1cmVBc3luYyAocGF0aDogc3RyaW5nKSB7XG5cdFx0cmV0dXJuIG5ldyBQcm9taXNlPFRleHR1cmU+KChyZXNvbHZlLCByZWplY3QpID0+IHtcblx0XHRcdHRoaXMubG9hZFRleHR1cmUocGF0aCxcblx0XHRcdFx0KF8sIHRleHR1cmUpID0+IHJlc29sdmUodGV4dHVyZSksXG5cdFx0XHRcdChfLCBtZXNzYWdlKSA9PiByZWplY3QobWVzc2FnZSksXG5cdFx0XHQpO1xuXHRcdH0pO1xuXHR9XG5cblx0YXN5bmMgbG9hZFRleHR1cmVBdGxhc0FzeW5jIChwYXRoOiBzdHJpbmcpIHtcblx0XHRyZXR1cm4gbmV3IFByb21pc2UoKHJlc29sdmUsIHJlamVjdCkgPT4ge1xuXHRcdFx0dGhpcy5sb2FkVGV4dHVyZUF0bGFzKHBhdGgsXG5cdFx0XHRcdChfLCBhdGxhcykgPT4gcmVzb2x2ZShhdGxhcyksXG5cdFx0XHRcdChfLCBtZXNzYWdlKSA9PiByZWplY3QobWVzc2FnZSksXG5cdFx0XHQpO1xuXHRcdH0pO1xuXHR9XG5cblx0YXN5bmMgbG9hZFRleHR1cmVBdGxhc0J1dE5vVGV4dHVyZXNBc3luYyAocGF0aDogc3RyaW5nKSB7XG5cdFx0cmV0dXJuIG5ldyBQcm9taXNlPFRleHR1cmVBdGxhcz4oKHJlc29sdmUsIHJlamVjdCkgPT4ge1xuXHRcdFx0dGhpcy5sb2FkVGV4dHVyZUF0bGFzQnV0Tm9UZXh0dXJlcyhwYXRoLFxuXHRcdFx0XHQoXywgYXRsYXMpID0+IHJlc29sdmUoYXRsYXMpLFxuXHRcdFx0XHQoXywgbWVzc2FnZSkgPT4gcmVqZWN0KG1lc3NhZ2UpLFxuXHRcdFx0KTtcblx0XHR9KTtcblx0fVxuXG5cdHNldENhY2hlIChjYWNoZTogQXNzZXRDYWNoZSkge1xuXHRcdHRoaXMuY2FjaGUgPSBjYWNoZTtcblx0fVxuXG5cdGdldCAocGF0aDogc3RyaW5nKSB7XG5cdFx0cmV0dXJuIHRoaXMuY2FjaGUuYXNzZXRzW3RoaXMucGF0aFByZWZpeCArIHBhdGhdO1xuXHR9XG5cblx0cmVxdWlyZSAocGF0aDogc3RyaW5nKSB7XG5cdFx0cGF0aCA9IHRoaXMucGF0aFByZWZpeCArIHBhdGg7XG5cdFx0bGV0IGFzc2V0ID0gdGhpcy5jYWNoZS5hc3NldHNbcGF0aF07XG5cdFx0aWYgKGFzc2V0KSByZXR1cm4gYXNzZXQ7XG5cdFx0bGV0IGVycm9yID0gdGhpcy5lcnJvcnNbcGF0aF07XG5cdFx0dGhyb3cgRXJyb3IoXCJBc3NldCBub3QgZm91bmQ6IFwiICsgcGF0aCArIChlcnJvciA/IFwiXFxuXCIgKyBlcnJvciA6IFwiXCIpKTtcblx0fVxuXG5cdHJlbW92ZSAocGF0aDogc3RyaW5nKSB7XG5cdFx0cGF0aCA9IHRoaXMucGF0aFByZWZpeCArIHBhdGg7XG5cdFx0bGV0IGFzc2V0ID0gdGhpcy5jYWNoZS5hc3NldHNbcGF0aF07XG5cdFx0aWYgKGFzc2V0LmRpc3Bvc2UpIGFzc2V0LmRpc3Bvc2UoKTtcblx0XHRkZWxldGUgdGhpcy5jYWNoZS5hc3NldHNbcGF0aF07XG5cdFx0ZGVsZXRlIHRoaXMuY2FjaGUuYXNzZXRzUmVmQ291bnRbcGF0aF07XG5cdFx0ZGVsZXRlIHRoaXMuY2FjaGUuYXNzZXRzTG9hZGVkW3BhdGhdO1xuXHRcdHJldHVybiBhc3NldDtcblx0fVxuXG5cdHJlbW92ZUFsbCAoKSB7XG5cdFx0Zm9yIChsZXQgcGF0aCBpbiB0aGlzLmNhY2hlLmFzc2V0cykge1xuXHRcdFx0bGV0IGFzc2V0ID0gdGhpcy5jYWNoZS5hc3NldHNbcGF0aF07XG5cdFx0XHRpZiAoYXNzZXQuZGlzcG9zZSkgYXNzZXQuZGlzcG9zZSgpO1xuXHRcdH1cblx0XHR0aGlzLmNhY2hlLmFzc2V0cyA9IHt9O1xuXHRcdHRoaXMuY2FjaGUuYXNzZXRzTG9hZGVkID0ge307XG5cdFx0dGhpcy5jYWNoZS5hc3NldHNSZWZDb3VudCA9IHt9O1xuXHR9XG5cblx0aXNMb2FkaW5nQ29tcGxldGUgKCk6IGJvb2xlYW4ge1xuXHRcdHJldHVybiB0aGlzLnRvTG9hZCA9PSAwO1xuXHR9XG5cblx0Z2V0VG9Mb2FkICgpOiBudW1iZXIge1xuXHRcdHJldHVybiB0aGlzLnRvTG9hZDtcblx0fVxuXG5cdGdldExvYWRlZCAoKTogbnVtYmVyIHtcblx0XHRyZXR1cm4gdGhpcy5sb2FkZWQ7XG5cdH1cblxuXHRkaXNwb3NlICgpIHtcblx0XHR0aGlzLnJlbW92ZUFsbCgpO1xuXHR9XG5cblx0Ly8gZGlzcG9zZSBhc3NldCBvbmx5IGlmIGl0J3Mgbm90IHVzZWQgYnkgb3RoZXJzXG5cdGRpc3Bvc2VBc3NldCAocGF0aDogc3RyaW5nKSB7XG5cdFx0Y29uc3QgYXNzZXQgPSB0aGlzLmNhY2hlLmFzc2V0c1twYXRoXTtcblx0XHRpZiAoYXNzZXQgaW5zdGFuY2VvZiBUZXh0dXJlQXRsYXMpIHtcblx0XHRcdGFzc2V0LmRpc3Bvc2UoKTtcblx0XHRcdHJldHVybjtcblx0XHR9XG5cdFx0dGhpcy5kaXNwb3NlQXNzZXRJbnRlcm5hbChwYXRoKTtcblx0fVxuXG5cdGhhc0Vycm9ycyAoKSB7XG5cdFx0cmV0dXJuIE9iamVjdC5rZXlzKHRoaXMuZXJyb3JzKS5sZW5ndGggPiAwO1xuXHR9XG5cblx0Z2V0RXJyb3JzICgpIHtcblx0XHRyZXR1cm4gdGhpcy5lcnJvcnM7XG5cdH1cblxuXHRwcml2YXRlIGRpc3Bvc2VBc3NldEludGVybmFsIChwYXRoOiBzdHJpbmcpIHtcblx0XHRpZiAodGhpcy5jYWNoZS5hc3NldHNSZWZDb3VudFtwYXRoXSA+IDAgJiYgLS10aGlzLmNhY2hlLmFzc2V0c1JlZkNvdW50W3BhdGhdID09PSAwKSB7XG5cdFx0XHRyZXR1cm4gdGhpcy5yZW1vdmUocGF0aCk7XG5cdFx0fVxuXHR9XG5cblx0cHJpdmF0ZSBjcmVhdGVUZXh0dXJlQXRsYXMgKHBhdGg6IHN0cmluZywgYXRsYXNUZXh0OiBzdHJpbmcpOiBUZXh0dXJlQXRsYXMge1xuXHRcdGNvbnN0IGF0bGFzID0gbmV3IFRleHR1cmVBdGxhcyhhdGxhc1RleHQpO1xuXHRcdGF0bGFzLmRpc3Bvc2UgPSAoKSA9PiB7XG5cdFx0XHRpZiAodGhpcy5jYWNoZS5hc3NldHNSZWZDb3VudFtwYXRoXSA8PSAwKSByZXR1cm47XG5cdFx0XHR0aGlzLmRpc3Bvc2VBc3NldEludGVybmFsKHBhdGgpO1xuXHRcdFx0Zm9yIChjb25zdCBwYWdlIG9mIGF0bGFzLnBhZ2VzKSB7XG5cdFx0XHRcdHBhZ2UudGV4dHVyZT8uZGlzcG9zZSgpO1xuXHRcdFx0fVxuXHRcdH1cblx0XHRyZXR1cm4gYXRsYXM7XG5cdH1cblxuXHRwcml2YXRlIGNyZWF0ZVRleHR1cmUgKHBhdGg6IHN0cmluZywgaW1hZ2U6IEhUTUxJbWFnZUVsZW1lbnQgfCBJbWFnZUJpdG1hcCk6IFRleHR1cmUge1xuXHRcdGNvbnN0IHRleHR1cmUgPSB0aGlzLnRleHR1cmVMb2FkZXIoaW1hZ2UpO1xuXHRcdGNvbnN0IHRleHR1cmVEaXNwb3NlID0gdGV4dHVyZS5kaXNwb3NlLmJpbmQodGV4dHVyZSk7XG5cdFx0dGV4dHVyZS5kaXNwb3NlID0gKCkgPT4ge1xuXHRcdFx0aWYgKHRoaXMuZGlzcG9zZUFzc2V0SW50ZXJuYWwocGF0aCkpIHRleHR1cmVEaXNwb3NlKCk7XG5cdFx0fVxuXHRcdHJldHVybiB0ZXh0dXJlO1xuXHR9XG59XG5cbmV4cG9ydCBjbGFzcyBBc3NldENhY2hlIHtcblx0cHVibGljIGFzc2V0czogU3RyaW5nTWFwPGFueT4gPSB7fTtcblx0cHVibGljIGFzc2V0c1JlZkNvdW50OiBTdHJpbmdNYXA8bnVtYmVyPiA9IHt9O1xuXHRwdWJsaWMgYXNzZXRzTG9hZGVkOiBTdHJpbmdNYXA8UHJvbWlzZTxhbnk+PiA9IHt9O1xuXG5cdHN0YXRpYyBBVkFJTEFCTEVfQ0FDSEVTID0gbmV3IE1hcDxzdHJpbmcsIEFzc2V0Q2FjaGU+KCk7XG5cdHN0YXRpYyBnZXRDYWNoZSAoaWQ6IHN0cmluZykge1xuXHRcdGNvbnN0IGNhY2hlID0gQXNzZXRDYWNoZS5BVkFJTEFCTEVfQ0FDSEVTLmdldChpZCk7XG5cdFx0aWYgKGNhY2hlKSByZXR1cm4gY2FjaGU7XG5cblx0XHRjb25zdCBuZXdDYWNoZSA9IG5ldyBBc3NldENhY2hlKCk7XG5cdFx0QXNzZXRDYWNoZS5BVkFJTEFCTEVfQ0FDSEVTLnNldChpZCwgbmV3Q2FjaGUpO1xuXHRcdHJldHVybiBuZXdDYWNoZTtcblx0fVxuXG5cdGFzeW5jIGFkZEFzc2V0IChwYXRoOiBzdHJpbmcsIGFzc2V0OiBhbnkpIHtcblx0XHR0aGlzLmFzc2V0c0xvYWRlZFtwYXRoXSA9IFByb21pc2UucmVzb2x2ZShhc3NldCk7XG5cdFx0dGhpcy5hc3NldHNbcGF0aF0gPSBhd2FpdCBhc3NldDtcblx0fVxufVxuXG5leHBvcnQgY2xhc3MgRG93bmxvYWRlciB7XG5cdHByaXZhdGUgY2FsbGJhY2tzOiBTdHJpbmdNYXA8QXJyYXk8RnVuY3Rpb24+PiA9IHt9O1xuXHRyYXdEYXRhVXJpczogU3RyaW5nTWFwPHN0cmluZz4gPSB7fTtcblxuXHRkYXRhVXJpVG9TdHJpbmcgKGRhdGFVcmk6IHN0cmluZykge1xuXHRcdGlmICghZGF0YVVyaS5zdGFydHNXaXRoKFwiZGF0YTpcIikpIHtcblx0XHRcdHRocm93IG5ldyBFcnJvcihcIk5vdCBhIGRhdGEgVVJJLlwiKTtcblx0XHR9XG5cblx0XHRsZXQgYmFzZTY0SWR4ID0gZGF0YVVyaS5pbmRleE9mKFwiYmFzZTY0LFwiKTtcblx0XHRpZiAoYmFzZTY0SWR4ICE9IC0xKSB7XG5cdFx0XHRiYXNlNjRJZHggKz0gXCJiYXNlNjQsXCIubGVuZ3RoO1xuXHRcdFx0cmV0dXJuIGF0b2IoZGF0YVVyaS5zdWJzdHIoYmFzZTY0SWR4KSk7XG5cdFx0fSBlbHNlIHtcblx0XHRcdHJldHVybiBkYXRhVXJpLnN1YnN0cihkYXRhVXJpLmluZGV4T2YoXCIsXCIpICsgMSk7XG5cdFx0fVxuXHR9XG5cblx0YmFzZTY0VG9VaW50OEFycmF5IChiYXNlNjQ6IHN0cmluZykge1xuXHRcdHZhciBiaW5hcnlfc3RyaW5nID0gd2luZG93LmF0b2IoYmFzZTY0KTtcblx0XHR2YXIgbGVuID0gYmluYXJ5X3N0cmluZy5sZW5ndGg7XG5cdFx0dmFyIGJ5dGVzID0gbmV3IFVpbnQ4QXJyYXkobGVuKTtcblx0XHRmb3IgKHZhciBpID0gMDsgaSA8IGxlbjsgaSsrKSB7XG5cdFx0XHRieXRlc1tpXSA9IGJpbmFyeV9zdHJpbmcuY2hhckNvZGVBdChpKTtcblx0XHR9XG5cdFx0cmV0dXJuIGJ5dGVzO1xuXHR9XG5cblx0ZGF0YVVyaVRvVWludDhBcnJheSAoZGF0YVVyaTogc3RyaW5nKSB7XG5cdFx0aWYgKCFkYXRhVXJpLnN0YXJ0c1dpdGgoXCJkYXRhOlwiKSkge1xuXHRcdFx0dGhyb3cgbmV3IEVycm9yKFwiTm90IGEgZGF0YSBVUkkuXCIpO1xuXHRcdH1cblxuXHRcdGxldCBiYXNlNjRJZHggPSBkYXRhVXJpLmluZGV4T2YoXCJiYXNlNjQsXCIpO1xuXHRcdGlmIChiYXNlNjRJZHggPT0gLTEpIHRocm93IG5ldyBFcnJvcihcIk5vdCBhIGJpbmFyeSBkYXRhIFVSSS5cIik7XG5cdFx0YmFzZTY0SWR4ICs9IFwiYmFzZTY0LFwiLmxlbmd0aDtcblx0XHRyZXR1cm4gdGhpcy5iYXNlNjRUb1VpbnQ4QXJyYXkoZGF0YVVyaS5zdWJzdHIoYmFzZTY0SWR4KSk7XG5cdH1cblxuXHRkb3dubG9hZFRleHQgKHVybDogc3RyaW5nLCBzdWNjZXNzOiAoZGF0YTogc3RyaW5nKSA9PiB2b2lkLCBlcnJvcjogKHN0YXR1czogbnVtYmVyLCByZXNwb25zZVRleHQ6IHN0cmluZykgPT4gdm9pZCkge1xuXHRcdGlmICh0aGlzLnN0YXJ0KHVybCwgc3VjY2VzcywgZXJyb3IpKSByZXR1cm47XG5cblx0XHRjb25zdCByYXdEYXRhVXJpID0gdGhpcy5yYXdEYXRhVXJpc1t1cmxdO1xuXHRcdC8vIHdlIGFzc3VtZSBpZiBhIFwiLlwiIGlzIGluY2x1ZGVkIGluIGEgcmF3IGRhdGEgdXJpLCBpdCBpcyB1c2VkIHRvIHJld3JpdGUgYW4gYXNzZXQgVVJMXG5cdFx0aWYgKHJhd0RhdGFVcmkgJiYgIXJhd0RhdGFVcmkuaW5jbHVkZXMoXCIuXCIpKSB7XG5cdFx0XHR0cnkge1xuXHRcdFx0XHR0aGlzLmZpbmlzaCh1cmwsIDIwMCwgdGhpcy5kYXRhVXJpVG9TdHJpbmcocmF3RGF0YVVyaSkpO1xuXHRcdFx0fSBjYXRjaCAoZSkge1xuXHRcdFx0XHR0aGlzLmZpbmlzaCh1cmwsIDQwMCwgSlNPTi5zdHJpbmdpZnkoZSkpO1xuXHRcdFx0fVxuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblxuXHRcdGxldCByZXF1ZXN0ID0gbmV3IFhNTEh0dHBSZXF1ZXN0KCk7XG5cdFx0cmVxdWVzdC5vdmVycmlkZU1pbWVUeXBlKFwidGV4dC9odG1sXCIpO1xuXHRcdHJlcXVlc3Qub3BlbihcIkdFVFwiLCByYXdEYXRhVXJpID8gcmF3RGF0YVVyaSA6IHVybCwgdHJ1ZSk7XG5cdFx0bGV0IGRvbmUgPSAoKSA9PiB7XG5cdFx0XHR0aGlzLmZpbmlzaCh1cmwsIHJlcXVlc3Quc3RhdHVzLCByZXF1ZXN0LnJlc3BvbnNlVGV4dCk7XG5cdFx0fTtcblx0XHRyZXF1ZXN0Lm9ubG9hZCA9IGRvbmU7XG5cdFx0cmVxdWVzdC5vbmVycm9yID0gZG9uZTtcblx0XHRyZXF1ZXN0LnNlbmQoKTtcblx0fVxuXG5cdGRvd25sb2FkSnNvbiAodXJsOiBzdHJpbmcsIHN1Y2Nlc3M6IChkYXRhOiBvYmplY3QpID0+IHZvaWQsIGVycm9yOiAoc3RhdHVzOiBudW1iZXIsIHJlc3BvbnNlVGV4dDogc3RyaW5nKSA9PiB2b2lkKSB7XG5cdFx0dGhpcy5kb3dubG9hZFRleHQodXJsLCAoZGF0YTogc3RyaW5nKTogdm9pZCA9PiB7XG5cdFx0XHRzdWNjZXNzKEpTT04ucGFyc2UoZGF0YSkpO1xuXHRcdH0sIGVycm9yKTtcblx0fVxuXG5cdGRvd25sb2FkQmluYXJ5ICh1cmw6IHN0cmluZywgc3VjY2VzczogKGRhdGE6IFVpbnQ4QXJyYXkpID0+IHZvaWQsIGVycm9yOiAoc3RhdHVzOiBudW1iZXIsIHJlc3BvbnNlVGV4dDogc3RyaW5nKSA9PiB2b2lkKSB7XG5cdFx0aWYgKHRoaXMuc3RhcnQodXJsLCBzdWNjZXNzLCBlcnJvcikpIHJldHVybjtcblxuXHRcdGNvbnN0IHJhd0RhdGFVcmkgPSB0aGlzLnJhd0RhdGFVcmlzW3VybF07XG5cdFx0Ly8gd2UgYXNzdW1lIGlmIGEgXCIuXCIgaXMgaW5jbHVkZWQgaW4gYSByYXcgZGF0YSB1cmksIGl0IGlzIHVzZWQgdG8gcmV3cml0ZSBhbiBhc3NldCBVUkxcblx0XHRpZiAocmF3RGF0YVVyaSAmJiAhcmF3RGF0YVVyaS5pbmNsdWRlcyhcIi5cIikpIHtcblx0XHRcdHRyeSB7XG5cdFx0XHRcdHRoaXMuZmluaXNoKHVybCwgMjAwLCB0aGlzLmRhdGFVcmlUb1VpbnQ4QXJyYXkocmF3RGF0YVVyaSkpO1xuXHRcdFx0fSBjYXRjaCAoZSkge1xuXHRcdFx0XHR0aGlzLmZpbmlzaCh1cmwsIDQwMCwgSlNPTi5zdHJpbmdpZnkoZSkpO1xuXHRcdFx0fVxuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblxuXHRcdGxldCByZXF1ZXN0ID0gbmV3IFhNTEh0dHBSZXF1ZXN0KCk7XG5cdFx0cmVxdWVzdC5vcGVuKFwiR0VUXCIsIHJhd0RhdGFVcmkgPyByYXdEYXRhVXJpIDogdXJsLCB0cnVlKTtcblx0XHRyZXF1ZXN0LnJlc3BvbnNlVHlwZSA9IFwiYXJyYXlidWZmZXJcIjtcblx0XHRsZXQgb25lcnJvciA9ICgpID0+IHtcblx0XHRcdHRoaXMuZmluaXNoKHVybCwgcmVxdWVzdC5zdGF0dXMsIHJlcXVlc3QucmVzcG9uc2UpO1xuXHRcdH07XG5cdFx0cmVxdWVzdC5vbmxvYWQgPSAoKSA9PiB7XG5cdFx0XHRpZiAocmVxdWVzdC5zdGF0dXMgPT0gMjAwIHx8IHJlcXVlc3Quc3RhdHVzID09IDApXG5cdFx0XHRcdHRoaXMuZmluaXNoKHVybCwgMjAwLCBuZXcgVWludDhBcnJheShyZXF1ZXN0LnJlc3BvbnNlIGFzIEFycmF5QnVmZmVyKSk7XG5cdFx0XHRlbHNlXG5cdFx0XHRcdG9uZXJyb3IoKTtcblx0XHR9O1xuXHRcdHJlcXVlc3Qub25lcnJvciA9IG9uZXJyb3I7XG5cdFx0cmVxdWVzdC5zZW5kKCk7XG5cdH1cblxuXHRwcml2YXRlIHN0YXJ0ICh1cmw6IHN0cmluZywgc3VjY2VzczogYW55LCBlcnJvcjogYW55KSB7XG5cdFx0bGV0IGNhbGxiYWNrcyA9IHRoaXMuY2FsbGJhY2tzW3VybF07XG5cdFx0dHJ5IHtcblx0XHRcdGlmIChjYWxsYmFja3MpIHJldHVybiB0cnVlO1xuXHRcdFx0dGhpcy5jYWxsYmFja3NbdXJsXSA9IGNhbGxiYWNrcyA9IFtdO1xuXHRcdH0gZmluYWxseSB7XG5cdFx0XHRjYWxsYmFja3MucHVzaChzdWNjZXNzLCBlcnJvcik7XG5cdFx0fVxuXHR9XG5cblx0cHJpdmF0ZSBmaW5pc2ggKHVybDogc3RyaW5nLCBzdGF0dXM6IG51bWJlciwgZGF0YTogYW55KSB7XG5cdFx0bGV0IGNhbGxiYWNrcyA9IHRoaXMuY2FsbGJhY2tzW3VybF07XG5cdFx0ZGVsZXRlIHRoaXMuY2FsbGJhY2tzW3VybF07XG5cdFx0bGV0IGFyZ3MgPSBzdGF0dXMgPT0gMjAwIHx8IHN0YXR1cyA9PSAwID8gW2RhdGFdIDogW3N0YXR1cywgZGF0YV07XG5cdFx0Zm9yIChsZXQgaSA9IGFyZ3MubGVuZ3RoIC0gMSwgbiA9IGNhbGxiYWNrcy5sZW5ndGg7IGkgPCBuOyBpICs9IDIpXG5cdFx0XHRjYWxsYmFja3NbaV0uYXBwbHkobnVsbCwgYXJncyk7XG5cdH1cbn1cbiJdfQ==