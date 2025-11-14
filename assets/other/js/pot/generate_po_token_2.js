const { generate } = require('youtube-po-token-generator')


const fs = require('fs');
(async function() {console.log(JSON.stringify(await generate().then())); })()

