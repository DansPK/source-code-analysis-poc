const express = require("express");
const searchRouter = require("./routes/search");

const app = express();
app.use("/search", searchRouter);

app.listen(3000);
