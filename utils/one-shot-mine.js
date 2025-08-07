const { generate } = require('../index')
const { formatError } = require('../lib/utils')


const fs = require('fs');
(async function() {console.log(JSON.stringify(await generate().then())); })()


