"use strict";
var bgutils_js_1 = require("bgutils-js");
var jsdom_1 = require("jsdom");
var youtubei_js_1 = require("youtubei.js");

// source https://github.com/alive4ever/bgutils-pot-generator/


async function generate_pot_identifier(identifier) {

  let innertube;
  const requestKey = 'O43z0dpjhgX20SCx4KAo';

  if (!identifier) {
    let innertube = await youtubei_js_1.Innertube.create({ retrieve_player: false });
    identifier = innertube.session.context.client.visitorData;
    if (!identifier) {throw new Error('Could not get visitor data');}
  }

  const dom = new jsdom_1.JSDOM();
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document
  });

  const bgConfig = {
    fetch: function (input, init) { return fetch(input, init); },
    globalObj: globalThis,
    identifier: identifier,
    requestKey: requestKey
  };

  const bgChallenge = await bgutils_js_1.BG.Challenge.create(bgConfig);

  if (!bgChallenge)
    throw new Error('Could not get challenge');

  const interpreterJavascript = bgChallenge.interpreterJavascript.privateDoNotAccessOrElseSafeScriptWrappedValue;

  if (interpreterJavascript) {
    new Function(interpreterJavascript)();
  } else throw new Error('Could not load VM');

  const poTokenResult = await bgutils_js_1.BG.PoToken.generate({
    program: bgChallenge.program,
    globalName: bgChallenge.globalName,
    bgConfig: bgConfig
  });

  const placeholderPoToken = bgutils_js_1.BG.PoToken.generatePlaceholder(identifier);

  var session_info = {
    visitorData: identifier,
    placeholderPoToken: placeholderPoToken,
    poToken: poTokenResult.poToken,
    integrityTokenData: poTokenResult.integrityTokenData
  };

  console.log(JSON.stringify(session_info));
}

var identifier;
if (process.argv.length > 2) {
    identifier = process.argv[2];
    if (identifier.length === 11) {
        // console.log('it is video_id')
    }
    else if (identifier.length > 42) {
        // console.log('it is visitor_data')
    }
    else {
        throw new Error('Invalid argument!');
    }
}

const session_info = generate_pot_identifier(identifier);
// console.log(JSON.stringify(session_info));
// execute .ts file: npx tsx generate-po-token.ts
// generate .js file: npx tsc generate-po-token.ts

